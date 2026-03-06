"""
Audiobook Maker V7 - Centralized Configuration

All configurable values with sensible defaults. Override via environment variables
where applicable (e.g., AUDIOBOOK_CACHE_MAX_MB=256).
"""

from __future__ import annotations

import os
from pathlib import Path

# Base paths (relative to project root)
BASE_DIR = Path(__file__).resolve().parent

# ─── Paths ─────────────────────────────────────────────────────────────────
CACHE_DIR = BASE_DIR / "tts_cache"
MANIFESTS_DIR = BASE_DIR / "manifests"
PRONUNCIATIONS_DIR = BASE_DIR / "pronunciations"
TEMP_DIR = BASE_DIR / "temp"
OUTPUT_DIR = BASE_DIR / "output"
BOOK_PROFILES_DIR = PRONUNCIATIONS_DIR / "book_profiles"
SAVED_INPUTS_DIR = BASE_DIR / "saved_inputs"
UI_DRAFT_PATH = BASE_DIR / "ui_draft.json"
APP_STATE_PATH = BASE_DIR / "app_state.json"

# ─── FFmpeg ─────────────────────────────────────────────────────────────────
DEFAULT_FFMPEG_TIMEOUT_S = int(os.environ.get("AUDIOBOOK_FFMPEG_TIMEOUT", "240"))
DEFAULT_FFMPEG_RETRIES = int(os.environ.get("AUDIOBOOK_FFMPEG_RETRIES", "2"))

# ─── Network & Fetch ───────────────────────────────────────────────────────
MAX_REMOTE_TEXT_BYTES = int(os.environ.get("AUDIOBOOK_MAX_REMOTE_BYTES", str(2 * 1024 * 1024)))
MAX_CLOUD_MANIFEST_BYTES = int(os.environ.get("AUDIOBOOK_MAX_CLOUD_BYTES", str(1024 * 1024)))
URL_FETCH_TIMEOUT_S = int(os.environ.get("AUDIOBOOK_URL_TIMEOUT", "20"))
URL_READ_CHUNK_SIZE = 65536

# ─── TTS & Generation ──────────────────────────────────────────────────────
# Characters per second estimates for ETA (Edge ~28, Kokoro ~16)
TTS_EDGE_CPS = int(os.environ.get("AUDIOBOOK_EDGE_CPS", "28"))
TTS_KOKORO_CPS = int(os.environ.get("AUDIOBOOK_KOKORO_CPS", "16"))
EDGE_TTS_MAX_CONCURRENT = 12
KOKORO_MAX_CONCURRENT = 1

# ─── Cache ──────────────────────────────────────────────────────────────────
CACHE_DEFAULT_MAX_MB = int(os.environ.get("AUDIOBOOK_CACHE_MAX_MB", "500"))
CACHE_MIN_MB = 128
CACHE_MAX_MB = 4096
CACHE_STEP_MB = 64

# ─── Text Processing ────────────────────────────────────────────────────────
CHUNK_MAX_CHARS = int(os.environ.get("AUDIOBOOK_CHUNK_MAX_CHARS", "5500"))
CHAPTER_MIN_GAP_CHARS = int(os.environ.get("AUDIOBOOK_CHAPTER_MIN_GAP", "200"))
DIALOGUE_CONTEXT_CHARS = int(os.environ.get("AUDIOBOOK_DIALOGUE_CONTEXT", "500"))
FIRST_CHUNK_PREVIEW_CHARS = 2000

# ─── UI & Voice Browser ─────────────────────────────────────────────────────
VOICE_BROWSER_PAGE_SIZE = int(os.environ.get("AUDIOBOOK_VOICE_PAGE_SIZE", "12"))
PREVIEW_SAMPLE_TEXT = (
    "This is a ten second voice preview for Audiobook Maker version seven. "
    "You are hearing the selected voice speaking naturally with clear pacing."
)
USER_AGENT = "AudiobookCreatorV7/1.0 (+mobile-safe-fetch)"

# ─── File Limits (Input Validation) ──────────────────────────────────────────
MAX_PDF_SIZE_MB = int(os.environ.get("AUDIOBOOK_MAX_PDF_MB", "500"))
MAX_EPUB_SIZE_MB = int(os.environ.get("AUDIOBOOK_MAX_EPUB_MB", "100"))

# ─── Preflight / Disk ───────────────────────────────────────────────────────
MIN_FREE_DISK_MB = int(os.environ.get("AUDIOBOOK_MIN_DISK_MB", "1024"))

# ─── App Metadata ────────────────────────────────────────────────────────────
APP_VERSION = "7.0"
CACHE_KEY_SCHEMA_VERSION = 2
