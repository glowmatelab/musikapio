#!/usr/bin/env bash
set -e

echo "📦 Installing Python dependencies..."
pip install -r requirements.txt

echo "🎬 Installing FFmpeg..."
mkdir -p /opt/ffmpeg
cd /opt/ffmpeg

# Static FFmpeg binary download karo (apt-get Render free pe kaam nahi karta)
curl -L https://github.com/yt-dlp/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-linux64-gpl.tar.xz \
  -o ffmpeg.tar.xz

tar -xf ffmpeg.tar.xz --strip-components=1
rm ffmpeg.tar.xz

# PATH mein add karo
export PATH="/opt/ffmpeg/bin:$PATH"
echo "export PATH=/opt/ffmpeg/bin:\$PATH" >> ~/.bashrc

echo "✅ FFmpeg version: $(ffmpeg -version | head -1)"
echo "✅ Build complete!"
