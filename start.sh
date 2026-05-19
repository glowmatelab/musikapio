#!/usr/bin/env bash
export PATH="/opt/ffmpeg/bin:$PATH"
exec uvicorn youtube_api_server:app --host 0.0.0.0 --port $PORT
