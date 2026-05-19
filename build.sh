#!/usr/bin/env bash
set -e

echo "📦 Installing Python dependencies..."
pip install -r requirements.txt

echo "🎬 Installing FFmpeg..."
mkdir -p $HOME/ffmpeg
cd $HOME/ffmpeg

curl -L https://github.com/yt-dlp/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-linux64-gpl.tar.xz \
  -o ffmpeg.tar.xz

tar -xf ffmpeg.tar.xz --strip-components=1
rm ffmpeg.tar.xz

echo "✅ FFmpeg version: $($HOME/ffmpeg/bin/ffmpeg -version | head -1)"
echo "✅ Build complete!"
