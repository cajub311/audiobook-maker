#!/usr/bin/env bash
# Audiobook Creator V7 — environment setup (Python deps + optional FFmpeg).
# All TTS engines in this project are free; no API keys required for the defaults.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

PYTHON="${PYTHON:-python3}"

echo "=== Audiobook Creator V7 setup ==="
echo ""

if ! command -v "$PYTHON" &>/dev/null; then
  echo "ERROR: $PYTHON not found. Install Python 3.10+ or set PYTHON= to your interpreter."
  exit 1
fi
echo "[OK] Python: $($PYTHON --version)"

have_ffmpeg() {
  command -v ffmpeg &>/dev/null && command -v ffprobe &>/dev/null
}

if have_ffmpeg; then
  echo "[OK] FFmpeg and ffprobe found"
else
  echo "[!!] FFmpeg not found (needed for MP3/M4B assembly)."
  if [[ "$(id -u)" -eq 0 ]]; then
    if command -v apt-get &>/dev/null; then
      apt-get update -qq && apt-get install -y -qq ffmpeg
    elif command -v dnf &>/dev/null; then
      dnf install -y ffmpeg
    elif command -v pacman &>/dev/null; then
      pacman -S --noconfirm ffmpeg
    else
      echo "Install FFmpeg from your OS packages or https://ffmpeg.org/download.html"
      exit 1
    fi
  elif command -v sudo &>/dev/null && command -v apt-get &>/dev/null; then
    echo "Attempting: sudo apt-get install -y ffmpeg"
    sudo apt-get update -qq && sudo apt-get install -y -qq ffmpeg
  elif command -v brew &>/dev/null; then
    echo "Attempting: brew install ffmpeg"
    brew install ffmpeg
  else
    echo "Install FFmpeg manually, then re-run this script."
    echo "  Debian/Ubuntu: sudo apt-get install -y ffmpeg"
    echo "  macOS:         brew install ffmpeg"
    exit 1
  fi
  if ! have_ffmpeg; then
    echo "ERROR: FFmpeg still not available after install attempt."
    exit 1
  fi
  echo "[OK] FFmpeg installed"
fi

echo ""
echo "Installing Python packages from requirements.txt ..."
"$PYTHON" -m pip install -q -r requirements.txt

echo ""
echo "Checking TTS engines..."
"$PYTHON" -c "
from tts.engines import engine_availability, auto_select_engine
avail = engine_availability()
for name, info in avail.items():
    status = 'READY' if info.get('ready') else 'NOT INSTALLED'
    print(f'  {name}: {status}')
    if info.get('fix'):
        print(f'    Fix: {info[\"fix\"]}')
print(f'  Auto-selected engine: {auto_select_engine()}')
print()
print('Engines above use free/local or no-account defaults where applicable.')
"

echo ""
echo "=== Setup complete ==="
echo "Start the Gradio app:"
echo "  $PYTHON audiobook_creator_v7.py"
echo ""
echo "Then open http://localhost:${GRADIO_SERVER_PORT:-7860}"
echo "Login defaults: GRADIO_AUTH_USER / GRADIO_AUTH_PASSWORD (see README)."
echo "Local dev without login: ABM_GRADIO_NO_AUTH=1 $PYTHON audiobook_creator_v7.py"
echo ""
