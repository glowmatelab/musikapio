#!/usr/bin/env bash
# FFmpeg path fix — build.sh HOME/ffmpeg mein install karta hai
export PATH="$HOME/ffmpeg/bin:/opt/ffmpeg/bin:$PATH"
exec uvicorn youtube_api_server:app --host 0.0.0.0 --port $PORT
