#!/usr/bin/env bash
# Audiobook Creator V7 - One-click setup
# All free, no API keys needed.
set -e

echo "=== Audiobook Creator V7 Setup ==="
echo ""

# Check Python
if ! command -v python3 &>/dev/null; then
    echo "ERROR: Python 3 is required. Install it first."
    exit 1
fi
echo "[OK] Python 3 found: $(python3 --version)"

# Check FFmpeg
if command -v ffmpeg &>/dev/null && command -v ffprobe &>/dev/null; then
    echo "[OK] FFmpeg found"
else
    echo "[!!] FFmpeg not found. Attempting install..."
    if command -v apt-get &>/dev/null; then
        sudo apt-get update -qq && sudo apt-get install -y -qq ffmpeg
    elif command -v brew &>/dev/null; then
        brew install ffmpeg
    elif command -v dnf &>/dev/null; then
        sudo dnf install -y ffmpeg
    elif command -v pacman &>/dev/null; then
        sudo pacman -S --noconfirm ffmpeg
    else
        echo "Please install FFmpeg manually: https://ffmpeg.org/download.html"
    fi
fi

# Install Python dependencies
echo ""
echo "Installing Python packages (all free)..."
pip install -q -r requirements.txt

# Verify engines
echo ""
echo "Checking TTS engines..."
python3 -c "
from tts.engines import engine_availability, auto_select_engine
avail = engine_availability()
for name, info in avail.items():
    status = 'READY' if info.get('ready') else 'NOT INSTALLED'
    print(f'  {name}: {status}')
    if info.get('fix'):
        print(f'    Fix: {info[\"fix\"]}')
print(f'  Auto-selected engine: {auto_select_engine()}')
print()
print('All engines are FREE - no API keys or accounts needed!')
"

echo ""
echo "=== Setup complete! ==="
echo ""
echo "Start the app:"
echo "  python3 audiobook_creator_v7.py"
echo ""
echo "Then open: http://localhost:7860"
echo "Login: admin / audiobook2024"
echo ""
echo "Everything is free. No API keys needed."
