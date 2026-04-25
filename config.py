from __future__ import annotations

import os
from pathlib import Path


def _env_int(name: str, default: int, *, minimum: int | None = None) -> int:
    raw = os.getenv(name)
    if raw is None:
        value = default
    else:
        try:
            value = int(raw.strip())
        except Exception:
            value = default
    if minimum is not None:
        return max(minimum, value)
    return value


def _env_str(name: str, default: str) -> str:
    value = os.getenv(name)
    return value if value is not None and value != "" else default


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_float(name: str, default: float, *, minimum: float | None = None) -> float:
    raw = os.getenv(name)
    if raw is None:
        value = default
    else:
        try:
            value = float(raw.strip())
        except Exception:
            value = default
    if minimum is not None:
        return max(minimum, value)
    return value


APP_VERSION = _env_str("ABM_APP_VERSION", "7.0")
CACHE_KEY_SCHEMA_VERSION = _env_int("ABM_CACHE_KEY_SCHEMA_VERSION", 2, minimum=1)

BASE_DIR = Path(_env_str("ABM_BASE_DIR", str(Path(__file__).resolve().parent))).resolve()
CACHE_DIR = BASE_DIR / _env_str("ABM_CACHE_DIRNAME", "tts_cache")
MANIFESTS_DIR = BASE_DIR / _env_str("ABM_MANIFESTS_DIRNAME", "manifests")
PRONUNCIATIONS_DIR = BASE_DIR / _env_str("ABM_PRONUNCIATIONS_DIRNAME", "pronunciations")
TEMP_DIR = BASE_DIR / _env_str("ABM_TEMP_DIRNAME", "temp")
OUTPUT_DIR = BASE_DIR / _env_str("ABM_OUTPUT_DIRNAME", "output")
BOOK_PROFILES_DIR = PRONUNCIATIONS_DIR / _env_str("ABM_BOOK_PROFILES_DIRNAME", "book_profiles")
MODELS_DIR = BASE_DIR / _env_str("ABM_MODELS_DIRNAME", "models")
SAVED_INPUTS_DIR = BASE_DIR / _env_str("ABM_SAVED_INPUTS_DIRNAME", "saved_inputs")
UI_DRAFT_PATH = BASE_DIR / _env_str("ABM_UI_DRAFT_FILENAME", "ui_draft.json")
APP_STATE_PATH = BASE_DIR / _env_str("ABM_APP_STATE_FILENAME", "app_state.json")

DEFAULT_FFMPEG_TIMEOUT_S = _env_int("ABM_FFMPEG_TIMEOUT_S", 240, minimum=1)
DEFAULT_FFMPEG_RETRIES = _env_int("ABM_FFMPEG_RETRIES", 2, minimum=0)
DEFAULT_URL_FETCH_TIMEOUT_S = _env_int("ABM_URL_FETCH_TIMEOUT_S", 20, minimum=1)
MAX_REMOTE_TEXT_BYTES = _env_int("ABM_MAX_REMOTE_TEXT_BYTES", 2 * 1024 * 1024, minimum=1024)
MAX_CLOUD_MANIFEST_BYTES = _env_int("ABM_MAX_CLOUD_MANIFEST_BYTES", 1024 * 1024, minimum=1024)
MAX_UPLOAD_FILE_BYTES = _env_int("ABM_MAX_UPLOAD_FILE_BYTES", 500 * 1024 * 1024, minimum=1024 * 1024)

DEFAULT_SEGMENT_CHUNK_CHARS = _env_int("ABM_DEFAULT_SEGMENT_CHUNK_CHARS", 5500, minimum=600)
DEFAULT_CACHE_MAX_SIZE_MB = _env_int("ABM_DEFAULT_CACHE_MAX_SIZE_MB", 500, minimum=64)
QUICK_CACHE_MAX_SIZE_MB = _env_int("ABM_QUICK_CACHE_MAX_SIZE_MB", 512, minimum=64)
LOW_MEMORY_QUEUE_SIZE = _env_int("ABM_LOW_MEMORY_QUEUE_SIZE", 8, minimum=1)
DEFAULT_QUEUE_SIZE = _env_int("ABM_DEFAULT_QUEUE_SIZE", 32, minimum=1)
VOICE_BROWSER_PAGE_SIZE = _env_int("ABM_VOICE_BROWSER_PAGE_SIZE", 12, minimum=1)
CACHE_SLIDER_MIN_MB = _env_int("ABM_CACHE_SLIDER_MIN_MB", 128, minimum=64)
CACHE_SLIDER_MAX_MB = _env_int("ABM_CACHE_SLIDER_MAX_MB", 4096, minimum=128)
CACHE_SLIDER_STEP_MB = _env_int("ABM_CACHE_SLIDER_STEP_MB", 64, minimum=1)
DEFAULT_TTS_MIN_REQUEST_INTERVAL_S = _env_float("ABM_TTS_MIN_REQUEST_INTERVAL_S", 0.15, minimum=0.0)
DEFAULT_DIALOGUE_STRATEGY = _env_str("ABM_DIALOGUE_STRATEGY", "auto")

USER_AGENT = _env_str("ABM_USER_AGENT", "AudiobookCreatorV7/1.0 (+mobile-safe-fetch)")

# Gradio desktop UI (audiobook_creator_v7.py). Set ABM_GRADIO_NO_AUTH=1 for local dev only.
GRADIO_AUTH_USER = _env_str("GRADIO_AUTH_USER", "admin")
GRADIO_AUTH_PASSWORD = _env_str("GRADIO_AUTH_PASSWORD", "audiobook2024")
GRADIO_NO_AUTH = _env_bool("ABM_GRADIO_NO_AUTH", False)
