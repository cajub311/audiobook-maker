"""Audiobook Creator V7 — Centralized configuration.

All runtime constants live here. Values can be overridden via environment
variables prefixed with ``ABM_`` so deployments can tune behavior without
changing source code.

Usage inside the main application::

    from config import DEFAULT_CACHE_MAX_SIZE_MB, GRADIO_SERVER_PORT
"""
from __future__ import annotations

import os
from pathlib import Path

# ── Application identity ──────────────────────────────────────────────────────
APP_VERSION = "7.0"
CACHE_KEY_SCHEMA_VERSION = 2

# ── Runtime directory layout ──────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent
CACHE_DIR = BASE_DIR / "tts_cache"
MANIFESTS_DIR = BASE_DIR / "manifests"
PRONUNCIATIONS_DIR = BASE_DIR / "pronunciations"
TEMP_DIR = BASE_DIR / "temp"
OUTPUT_DIR = BASE_DIR / "output"
BOOK_PROFILES_DIR = PRONUNCIATIONS_DIR / "book_profiles"
SAVED_INPUTS_DIR = BASE_DIR / "saved_inputs"
UI_DRAFT_PATH = BASE_DIR / "ui_draft.json"
APP_STATE_PATH = BASE_DIR / "app_state.json"

# ── FFmpeg ────────────────────────────────────────────────────────────────────
# Increase ABM_FFMPEG_TIMEOUT_S on slow machines with large books.
DEFAULT_FFMPEG_TIMEOUT_S: int = int(os.getenv("ABM_FFMPEG_TIMEOUT_S", "240"))
DEFAULT_FFMPEG_RETRIES: int = int(os.getenv("ABM_FFMPEG_RETRIES", "2"))

# ── Networking / fetch limits ─────────────────────────────────────────────────
# Maximum bytes fetched from a remote URL for book text extraction.
MAX_REMOTE_TEXT_BYTES: int = int(os.getenv("ABM_MAX_REMOTE_TEXT_BYTES", str(2 * 1024 * 1024)))
# Maximum bytes accepted when restoring a cloud manifest backup.
MAX_CLOUD_MANIFEST_BYTES: int = int(os.getenv("ABM_MAX_CLOUD_MANIFEST_BYTES", str(1024 * 1024)))
# Uploaded files larger than this are rejected before processing (default 500 MB).
MAX_UPLOAD_FILE_BYTES: int = int(os.getenv("ABM_MAX_UPLOAD_FILE_BYTES", str(500 * 1024 * 1024)))
# HTTP timeout for URL-based text fetches.
URL_FETCH_TIMEOUT_S: int = int(os.getenv("ABM_URL_FETCH_TIMEOUT_S", "30"))
USER_AGENT = "AudiobookCreatorV7/1.0 (+mobile-safe-fetch)"

# ── TTS / cache ───────────────────────────────────────────────────────────────
VOICE_BROWSER_PAGE_SIZE: int = int(os.getenv("ABM_VOICE_BROWSER_PAGE_SIZE", "12"))
DEFAULT_CACHE_MAX_SIZE_MB: int = int(os.getenv("ABM_CACHE_MAX_SIZE_MB", "500"))
DEFAULT_MAX_QUEUE_SIZE: int = int(os.getenv("ABM_MAX_QUEUE_SIZE", "32"))
# Hard cap on chapters parsed from a single source document.
DEFAULT_MAX_CHAPTERS: int = int(os.getenv("ABM_MAX_CHAPTERS", "100"))
# Maximum characters per TTS segment chunk.
DEFAULT_CHUNK_MAX_CHARS: int = int(os.getenv("ABM_CHUNK_MAX_CHARS", "5500"))

# Characters-per-second throughput used for ETA estimates only.
TTS_CHARS_PER_SECOND_CLOUD: int = int(os.getenv("ABM_TTS_CPS_CLOUD", "28"))
TTS_CHARS_PER_SECOND_LOCAL: int = int(os.getenv("ABM_TTS_CPS_LOCAL", "16"))

# ── Audiobook assembly ────────────────────────────────────────────────────────
DEFAULT_LOUDNESS_LUFS: float = float(os.getenv("ABM_LOUDNESS_LUFS", "-19.0"))
# Silence gaps inserted between structural elements of the assembled audiobook.
DEFAULT_SILENCE_PARAGRAPH_S: float = float(os.getenv("ABM_SILENCE_PARAGRAPH_S", "0.5"))
DEFAULT_SILENCE_SCENE_S: float = float(os.getenv("ABM_SILENCE_SCENE_S", "1.0"))
DEFAULT_SILENCE_CHAPTER_S: float = float(os.getenv("ABM_SILENCE_CHAPTER_S", "2.0"))
DEFAULT_SILENCE_DIALOGUE_S: float = float(os.getenv("ABM_SILENCE_DIALOGUE_S", "0.3"))

# ── UI / preview ──────────────────────────────────────────────────────────────
PREVIEW_SAMPLE_TEXT = (
    "This is a ten second voice preview for Audiobook Maker version seven. "
    "You are hearing the selected voice speaking naturally with clear pacing."
)

# ── Gradio server ─────────────────────────────────────────────────────────────
GRADIO_SERVER_PORT: int = int(os.getenv("ABM_GRADIO_PORT", "7860"))
