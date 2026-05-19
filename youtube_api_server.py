"""
YouTube Download API Server — Render Edition (with cookies)
"""

import os
import asyncio
import hashlib
import time
import logging
from pathlib import Path
from contextlib import asynccontextmanager

import yt_dlp
import aiohttp
from fastapi import FastAPI, HTTPException, Query, BackgroundTasks
from fastapi.responses import FileResponse
import uvicorn

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger("YT-API")

DOWNLOADS_DIR    = Path("downloads")
DOWNLOADS_DIR.mkdir(exist_ok=True)

COOKIES_FILE     = Path("cookies.txt")  # GitHub repo se aayegi

TOKEN_TTL        = 600
KEEP_ALIVE_EVERY = 840
MAX_FILE_AGE_HRS = 1
PORT             = int(os.getenv("PORT", "8000"))
SELF_URL         = os.getenv("RENDER_EXTERNAL_URL", "")

token_store:    dict = {}
download_locks: dict = {}
DOWNLOAD_SEMAPHORE = asyncio.Semaphore(3)


async def keep_alive_task():
    if not SELF_URL:
        logger.info("ℹ️ Keep-alive disabled (RENDER_EXTERNAL_URL not set)")
        return
    await asyncio.sleep(30)
    logger.info(f"💓 Keep-alive started → {SELF_URL}/health")
    async with aiohttp.ClientSession() as session:
        while True:
            try:
                async with session.get(f"{SELF_URL}/health", timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    logger.info(f"💓 Keep-alive: HTTP {resp.status}")
            except Exception as e:
                logger.warning(f"⚠️ Keep-alive failed: {e}")
            await asyncio.sleep(KEEP_ALIVE_EVERY)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 Server starting...")
    if COOKIES_FILE.exists():
        logger.info(f"🍪 Cookies file found: {COOKIES_FILE}")
    else:
        logger.warning("⚠️ cookies.txt not found — YouTube may block downloads!")
    asyncio.create_task(keep_alive_task())
    yield
    logger.info("🛑 Server shutting down")


app = FastAPI(title="YouTube Download API", version="1.0.0", lifespan=lifespan)


def generate_token(video_id: str, file_type: str) -> str:
    token = hashlib.sha256(f"{video_id}:{file_type}:{time.time()}".encode()).hexdigest()[:32]
    token_store[token] = {"video_id": video_id, "type": file_type, "expires": time.time() + TOKEN_TTL}
    return token

def validate_token(token: str) -> dict | None:
    data = token_store.get(token)
    if not data: return None
    if time.time() > data["expires"]:
        del token_store[token]
        return None
    return data

def get_file_path(video_id: str, file_type: str) -> Path:
    return DOWNLOADS_DIR / f"{video_id}.{'mp4' if file_type == 'video' else 'mp3'}"

def cleanup_old_tokens():
    now = time.time()
    for k in [k for k, v in token_store.items() if v["expires"] < now]:
        del token_store[k]

def cleanup_old_files():
    cutoff = time.time() - (MAX_FILE_AGE_HRS * 3600)
    for f in DOWNLOADS_DIR.iterdir():
        if f.is_file() and f.stat().st_mtime < cutoff:
            try: f.unlink(); logger.info(f"🗑️ Deleted: {f.name}")
            except: pass

def _yt_dlp_download(url: str, opts: dict):
    with yt_dlp.YoutubeDL(opts) as ydl:
        ydl.download([url])

def get_ydl_opts(video_id: str, file_type: str) -> dict:
    """yt-dlp options — cookies se YouTube bot detection bypass karo."""
    base = {
        "outtmpl":     str(DOWNLOADS_DIR / f"{video_id}.%(ext)s"),
        "quiet":       True,
        "no_warnings": True,
        "noprogress":  True,
    }

    # Cookies file hai toh use karo
    if COOKIES_FILE.exists():
        base["cookiefile"] = str(COOKIES_FILE)

    if file_type == "video":
        base.update({
            "format":              "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720]",
            "merge_output_format": "mp4",
        })
    else:
        base.update({
            "format":         "bestaudio[ext=m4a]/bestaudio/best",
            "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "128"}],
        })

    return base

async def download_youtube(video_id: str, file_type: str) -> Path | None:
    file_path = get_file_path(video_id, file_type)
    yt_url    = f"https://www.youtube.com/watch?v={video_id}"

    if file_path.exists() and file_path.stat().st_size > 0:
        logger.info(f"✅ Cache hit: {file_path.name}")
        return file_path

    if video_id not in download_locks:
        download_locks[video_id] = asyncio.Lock()

    async with download_locks[video_id]:
        if file_path.exists() and file_path.stat().st_size > 0:
            return file_path

        logger.info(f"⬇️ Downloading {file_type}: {video_id}")
        ydl_opts = get_ydl_opts(video_id, file_type)

        try:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, lambda: _yt_dlp_download(yt_url, ydl_opts))
            if file_path.exists() and file_path.stat().st_size > 0:
                logger.info(f"✅ Done: {file_path.name} ({file_path.stat().st_size // 1024} KB)")
                return file_path
            logger.error("❌ File empty after download")
            return None
        except Exception as e:
            logger.error(f"❌ yt-dlp error: {e}")
            file_path.unlink(missing_ok=True)
            return None

async def get_live_stream_url(video_id: str) -> str | None:
    try:
        opts = {"quiet": True, "no_warnings": True, "skip_download": True, "format": "best"}
        if COOKIES_FILE.exists():
            opts["cookiefile"] = str(COOKIES_FILE)

        loop = asyncio.get_running_loop()
        def _extract():
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=False)
                return info.get("url") or info.get("manifest_url")
        return await loop.run_in_executor(None, _extract)
    except Exception as e:
        logger.error(f"❌ Live extract failed: {e}")
        return None


@app.get("/health")
async def health():
    cleanup_old_tokens()
    files    = [f for f in DOWNLOADS_DIR.iterdir() if f.is_file()]
    total_mb = sum(f.stat().st_size for f in files) // (1024 * 1024)
    return {
        "status":        "ok",
        "cookies":       COOKIES_FILE.exists(),
        "cached_files":  len(files),
        "disk_used_mb":  total_mb,
        "active_tokens": len(token_store),
    }

@app.get("/download")
async def get_download_token(url: str = Query(...), type: str = Query("audio")):
    video_id = url.strip()
    if not video_id:
        raise HTTPException(status_code=400, detail="video_id required")
    cleanup_old_tokens()
    token = generate_token(video_id, "video" if type == "video" else "audio")
    logger.info(f"🎫 Token: {video_id} ({type})")
    return {"download_token": token}

@app.get("/stream/{video_id}")
async def stream_file(video_id: str, type: str = Query("audio"), token: str = Query(...), background_tasks: BackgroundTasks = None):
    data = validate_token(token)
    if not data:
        raise HTTPException(status_code=401, detail="Token invalid ya expired")
    if data["video_id"] != video_id:
        raise HTTPException(status_code=403, detail="Token mismatch")

    async with DOWNLOAD_SEMAPHORE:
        file_path = await download_youtube(video_id, data["type"])

    if not file_path or not file_path.exists():
        raise HTTPException(status_code=500, detail="Download fail ho gaya")

    token_store.pop(token, None)
    if background_tasks:
        background_tasks.add_task(cleanup_old_files)

    return FileResponse(str(file_path), media_type="video/mp4" if data["type"] == "video" else "audio/mpeg", filename=file_path.name)

@app.get("/live")
async def live_stream(url: str = Query(...), type: str = Query("live")):
    stream_url = await get_live_stream_url(url.strip())
    if not stream_url:
        raise HTTPException(status_code=500, detail="Live URL nahi mila")
    return {"stream_url": stream_url}


if __name__ == "__main__":
    uvicorn.run("youtube_api_server:app", host="0.0.0.0", port=PORT, log_level="info")
