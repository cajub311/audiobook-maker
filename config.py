"""
Configuration management for Audiobook Creator V7

Centralized configuration with environment variable overrides.
All values can be overridden via environment variables in the format: ABM_SETTING_NAME
"""

import os
from pathlib import Path

# ============================================================================
# Application Settings
# ============================================================================

APP_VERSION = os.getenv("ABM_APP_VERSION", "7.0")
APP_NAME = "Audiobook Creator V7"

# ============================================================================
# Directory Configuration
# ============================================================================

BASE_DIR = Path(__file__).resolve().parent
CACHE_DIR = Path(os.getenv("ABM_CACHE_DIR", BASE_DIR / "tts_cache"))
MANIFESTS_DIR = Path(os.getenv("ABM_MANIFESTS_DIR", BASE_DIR / "manifests"))
PRONUNCIATIONS_DIR = Path(os.getenv("ABM_PRONUNCIATIONS_DIR", BASE_DIR / "pronunciations"))
TEMP_DIR = Path(os.getenv("ABM_TEMP_DIR", BASE_DIR / "temp"))
OUTPUT_DIR = Path(os.getenv("ABM_OUTPUT_DIR", BASE_DIR / "output"))
BOOK_PROFILES_DIR = PRONUNCIATIONS_DIR / "book_profiles"
SAVED_INPUTS_DIR = Path(os.getenv("ABM_SAVED_INPUTS_DIR", BASE_DIR / "saved_inputs"))

# State files
UI_DRAFT_PATH = BASE_DIR / "ui_draft.json"
APP_STATE_PATH = BASE_DIR / "app_state.json"

# ============================================================================
# FFmpeg Configuration
# ============================================================================

DEFAULT_FFMPEG_TIMEOUT_S = int(os.getenv("ABM_FFMPEG_TIMEOUT", "240"))
DEFAULT_FFMPEG_RETRIES = int(os.getenv("ABM_FFMPEG_RETRIES", "2"))

# ============================================================================
# API and Network Configuration
# ============================================================================

MAX_REMOTE_TEXT_BYTES = int(os.getenv("ABM_MAX_REMOTE_TEXT_BYTES", 2 * 1024 * 1024))  # 2MB
MAX_CLOUD_MANIFEST_BYTES = int(os.getenv("ABM_MAX_CLOUD_MANIFEST_BYTES", 1024 * 1024))  # 1MB
MAX_FILE_UPLOAD_MB = int(os.getenv("ABM_MAX_FILE_UPLOAD_MB", "500"))
URL_FETCH_TIMEOUT_S = int(os.getenv("ABM_URL_FETCH_TIMEOUT", "15"))
USER_AGENT = os.getenv("ABM_USER_AGENT", "AudiobookCreatorV7/1.0 (+mobile-safe-fetch)")

# ============================================================================
# TTS Configuration
# ============================================================================

# Edge TTS (Cloud)
EDGE_TTS_CHAR_PER_SEC = float(os.getenv("ABM_EDGE_TTS_SPEED", "28"))  # Approximate speed
EDGE_TTS_TIMEOUT_S = int(os.getenv("ABM_EDGE_TTS_TIMEOUT", "30"))

# Kokoro TTS (Offline)
KOKORO_CHAR_PER_SEC = float(os.getenv("ABM_KOKORO_SPEED", "16"))  # Approximate speed

# ============================================================================
# Cache Configuration
# ============================================================================

CACHE_SIZE_GB = int(os.getenv("ABM_CACHE_SIZE_GB", "100"))
CACHE_MAX_ENTRIES = int(os.getenv("ABM_CACHE_MAX_ENTRIES", "5000"))
VOICE_BROWSER_PAGE_SIZE = int(os.getenv("ABM_VOICE_BROWSER_PAGE_SIZE", "12"))

# ============================================================================
# Processing Configuration
# ============================================================================

MAX_CHAPTERS = int(os.getenv("ABM_MAX_CHAPTERS", "100"))
PREVIEW_SAMPLE_TEXT = (
    "This is a ten second voice preview for Audiobook Maker version seven. "
    "You are hearing the selected voice speaking naturally with clear pacing."
)
PREVIEW_SAMPLE_LENGTH_S = 10

# Dialogue Detection
ENABLE_DIALOGUE_DETECTION = os.getenv("ABM_ENABLE_DIALOGUE_DETECTION", "true").lower() == "true"
DIALOGUE_DETECTION_STRATEGIES = ["regex", "quote-pattern", "spacy"]  # In order of preference
DIALOGUE_CONFIDENCE_THRESHOLD = float(os.getenv("ABM_DIALOGUE_CONFIDENCE_THRESHOLD", "0.6"))

# ============================================================================
# UI Configuration
# ============================================================================

MOBILE_MODE_DEFAULT = os.getenv("ABM_MOBILE_MODE_DEFAULT", "true").lower() == "true"
SHOW_ADVANCED_TAB = os.getenv("ABM_SHOW_ADVANCED_TAB", "true").lower() == "true"
ENABLE_CLOUD_BACKUP = os.getenv("ABM_ENABLE_CLOUD_BACKUP", "true").lower() == "true"

# ============================================================================
# Validation Configuration
# ============================================================================

VALIDATE_URL_SAFETY = os.getenv("ABM_VALIDATE_URL_SAFETY", "true").lower() == "true"
BLOCK_PRIVATE_NETWORKS = os.getenv("ABM_BLOCK_PRIVATE_NETWORKS", "true").lower() == "true"
ENABLE_RATE_LIMITING = os.getenv("ABM_ENABLE_RATE_LIMITING", "false").lower() == "true"
RATE_LIMIT_REQUESTS_PER_MINUTE = int(os.getenv("ABM_RATE_LIMIT_RPM", "60"))

# ============================================================================
# Helper Functions
# ============================================================================

def ensure_runtime_dirs() -> None:
    """Create all required runtime directories."""
    for directory in (
        CACHE_DIR,
        MANIFESTS_DIR,
        PRONUNCIATIONS_DIR,
        TEMP_DIR,
        OUTPUT_DIR,
        BOOK_PROFILES_DIR,
        SAVED_INPUTS_DIR,
    ):
        directory.mkdir(parents=True, exist_ok=True)


def get_cache_schema_version() -> int:
    """Get cache key schema version for invalidation."""
    return 2


__all__ = [
    "APP_VERSION",
    "APP_NAME",
    "BASE_DIR",
    "CACHE_DIR",
    "MANIFESTS_DIR",
    "PRONUNCIATIONS_DIR",
    "TEMP_DIR",
    "OUTPUT_DIR",
    "BOOK_PROFILES_DIR",
    "SAVED_INPUTS_DIR",
    "UI_DRAFT_PATH",
    "APP_STATE_PATH",
    "DEFAULT_FFMPEG_TIMEOUT_S",
    "DEFAULT_FFMPEG_RETRIES",
    "MAX_REMOTE_TEXT_BYTES",
    "MAX_CLOUD_MANIFEST_BYTES",
    "MAX_FILE_UPLOAD_MB",
    "URL_FETCH_TIMEOUT_S",
    "USER_AGENT",
    "EDGE_TTS_CHAR_PER_SEC",
    "KOKORO_CHAR_PER_SEC",
    "CACHE_SIZE_GB",
    "CACHE_MAX_ENTRIES",
    "VOICE_BROWSER_PAGE_SIZE",
    "MAX_CHAPTERS",
    "PREVIEW_SAMPLE_TEXT",
    "PREVIEW_SAMPLE_LENGTH_S",
    "ENABLE_DIALOGUE_DETECTION",
    "DIALOGUE_DETECTION_STRATEGIES",
    "DIALOGUE_CONFIDENCE_THRESHOLD",
    "MOBILE_MODE_DEFAULT",
    "SHOW_ADVANCED_TAB",
    "ENABLE_CLOUD_BACKUP",
    "VALIDATE_URL_SAFETY",
    "BLOCK_PRIVATE_NETWORKS",
    "ENABLE_RATE_LIMITING",
    "RATE_LIMIT_REQUESTS_PER_MINUTE",
    "ensure_runtime_dirs",
    "get_cache_schema_version",
]
