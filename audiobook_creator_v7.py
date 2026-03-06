#!/usr/bin/env python3
"""
Audiobook Creator V7

Single-file manifest-based audiobook pipeline with:
- Stage 1 parse: source -> manifest
- Stage 2 generate: manifest -> per-segment audio cache
- Stage 3 assemble: cached segments -> final audiobook
"""

from __future__ import annotations

import asyncio
import contextlib
import gc
import hashlib
import ipaddress
import json
import os
import re
import shutil
import socket
import subprocess
import tempfile
import threading
import time
import uuid
import wave
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional
from urllib.parse import urlparse
from urllib.request import Request, urlopen


APP_VERSION = "7.0"
CACHE_KEY_SCHEMA_VERSION = 2
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
DEFAULT_FFMPEG_TIMEOUT_S = 240
DEFAULT_FFMPEG_RETRIES = 2
MAX_REMOTE_TEXT_BYTES = 2 * 1024 * 1024
MAX_CLOUD_MANIFEST_BYTES = 1024 * 1024
USER_AGENT = "AudiobookCreatorV7/1.0 (+mobile-safe-fetch)"
VOICE_BROWSER_PAGE_SIZE = 12
PREVIEW_SAMPLE_TEXT = (
    "This is a ten second voice preview for Audiobook Maker version seven. "
    "You are hearing the selected voice speaking naturally with clear pacing."
)


def ensure_runtime_dirs() -> None:
    for directory in (CACHE_DIR, MANIFESTS_DIR, PRONUNCIATIONS_DIR, TEMP_DIR, OUTPUT_DIR, BOOK_PROFILES_DIR, SAVED_INPUTS_DIR):
        directory.mkdir(parents=True, exist_ok=True)


def slugify(value: str, fallback: str = "book") -> str:
    clean = re.sub(r"[^A-Za-z0-9._-]+", "_", (value or "").strip())
    clean = clean.strip("._")
    return clean or fallback


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def run_command(
    command: list[str],
    check: bool = True,
    timeout_s: Optional[int] = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, check=check, capture_output=True, text=True, timeout=timeout_s)


def run_ffmpeg(
    command: list[str],
    timeout_s: int = DEFAULT_FFMPEG_TIMEOUT_S,
    retries: int = DEFAULT_FFMPEG_RETRIES,
) -> subprocess.CompletedProcess[str]:
    last_error: Optional[Exception] = None
    for attempt in range(retries + 1):
        try:
            return run_command(command, check=True, timeout_s=timeout_s)
        except Exception as exc:
            last_error = exc
            if attempt < retries:
                time.sleep(0.5 * (attempt + 1))
    raise RuntimeError(f"FFmpeg command failed after retries: {' '.join(command)} ({last_error})")


def ffmpeg_exists() -> bool:
    return shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


def get_duration_ffprobe(path: str) -> float:
    probe = shutil.which("ffprobe")
    if probe:
        try:
            result = run_command(
                [
                    probe,
                    "-v",
                    "error",
                    "-show_entries",
                    "format=duration",
                    "-of",
                    "default=noprint_wrappers=1:nokey=1",
                    path,
                ]
            )
            return float(result.stdout.strip() or 0.0)
        except Exception:
            pass

    # WAV fallback
    try:
        with contextlib.closing(wave.open(path, "rb")) as wf:
            frames = wf.getnframes()
            rate = wf.getframerate()
            return float(frames) / float(rate or 1)
    except Exception:
        return 0.0


def atomic_json_write(path: Path, payload: dict[str, Any], keep_backup: bool = True) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if keep_backup and path.exists():
        backup_path = path.with_suffix(path.suffix + ".bak")
        with contextlib.suppress(Exception):
            shutil.copy2(path, backup_path)
    with tempfile.NamedTemporaryFile("w", delete=False, dir=str(path.parent), encoding="utf-8") as tmp:
        json.dump(payload, tmp, indent=2, ensure_ascii=False)
        tmp.flush()
        os.fsync(tmp.fileno())
        temp_name = tmp.name
    os.replace(temp_name, path)


def save_manifest(manifest: dict[str, Any], manifest_path: str | Path) -> None:
    path = Path(manifest_path)
    atomic_json_write(path, manifest, keep_backup=True)
    backup_path = path.with_suffix(path.suffix + ".bak")
    with contextlib.suppress(Exception):
        shutil.copy2(path, backup_path)


def load_manifest(manifest_path: str | Path) -> dict[str, Any]:
    path = Path(manifest_path)
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        backup_path = path.with_suffix(path.suffix + ".bak")
        if backup_path.exists():
            with open(backup_path, "r", encoding="utf-8") as f:
                recovered = json.load(f)
            with contextlib.suppress(Exception):
                atomic_json_write(path, recovered, keep_backup=False)
            return recovered
        raise


def hash_dict(payload: dict[str, Any]) -> str:
    normalized = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.md5(normalized.encode("utf-8")).hexdigest()


def file_sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _load_json_dict(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            payload = json.load(f)
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def load_ui_draft() -> dict[str, Any]:
    return _load_json_dict(UI_DRAFT_PATH)


def save_ui_draft(draft: dict[str, Any]) -> None:
    atomic_json_write(UI_DRAFT_PATH, draft, keep_backup=True)


def load_app_state() -> dict[str, Any]:
    return _load_json_dict(APP_STATE_PATH)


def save_app_state(state: dict[str, Any]) -> None:
    payload = dict(state)
    payload["updated_at"] = now_iso()
    atomic_json_write(APP_STATE_PATH, payload, keep_backup=True)


def remember_last_project(project_id: str, manifest_path: str, cloud_url: Optional[str] = None) -> None:
    state = load_app_state()
    state["last_project_id"] = project_id
    state["last_manifest_path"] = manifest_path
    if cloud_url is not None and str(cloud_url).strip():
        state["last_cloud_url"] = str(cloud_url).strip()
    save_app_state(state)


def existing_path_or_empty(path: str) -> str:
    return path if path and Path(path).exists() else ""


def copy_uploaded_input(file_obj: Any, slot: str) -> str:
    src_path = getattr(file_obj, "name", None) if file_obj else None
    if not src_path:
        return ""
    src = Path(src_path)
    if not src.exists():
        return ""
    ext = src.suffix.lower() or ".txt"
    target = SAVED_INPUTS_DIR / f"{slugify(slot, fallback='input')}_{uuid.uuid4().hex[:10]}{ext}"
    shutil.copy2(src, target)
    return str(target)


def make_book_profile_key(book: dict[str, Any]) -> str:
    title = str(book.get("title", "untitled") or "untitled")
    author = str(book.get("author", "unknown") or "unknown")
    source_type = str(book.get("source_type", "text") or "text")
    return slugify(f"{title}_{author}_{source_type}", fallback="book_profile")


def load_book_profile(book_key: str) -> dict[str, Any]:
    profile_path = BOOK_PROFILES_DIR / f"{slugify(book_key)}.json"
    return _load_json_dict(profile_path)


def save_book_profile(
    book_key: str,
    character_voices: dict[str, Any],
    pronunciation_overrides: dict[str, str],
) -> None:
    profile_path = BOOK_PROFILES_DIR / f"{slugify(book_key)}.json"
    payload = {
        "character_voices": character_voices or {},
        "pronunciation_overrides": pronunciation_overrides or {},
        "updated_at": now_iso(),
    }
    atomic_json_write(profile_path, payload, keep_backup=True)


def pronunciation_overrides_to_rows(overrides: dict[str, str]) -> list[list[str]]:
    rows: list[list[str]] = []
    for word, repl in sorted((overrides or {}).items(), key=lambda item: item[0].lower()):
        rows.append([str(word), str(repl)])
    return rows


def choose_resume_project_id(
    inventory: dict[str, dict[str, str]],
    selected_project: Optional[str] = None,
    prefer_last: bool = False,
) -> Optional[str]:
    if selected_project and selected_project in inventory and not prefer_last:
        return selected_project
    state = load_app_state()
    last_id = str(state.get("last_project_id", "") or "")
    if last_id and last_id in inventory:
        return last_id
    last_manifest_path = str(state.get("last_manifest_path", "") or "")
    if last_manifest_path:
        for key, meta in inventory.items():
            if meta.get("manifest_path") == last_manifest_path:
                return key
    return next(iter(inventory.keys()), None)


def advisory_file_lock(lock_path: Path):
    @contextlib.contextmanager
    def _lock():
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        with open(lock_path, "a+", encoding="utf-8") as lock_file:
            try:
                import fcntl  # type: ignore

                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
                try:
                    yield
                finally:
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
            except Exception:
                # Non-posix fallback; best-effort lock.
                yield

    return _lock()


def _host_matches_allowed(hostname: str, allowed_hosts: set[str]) -> bool:
    host = hostname.lower().strip(".")
    return any(host == allowed or host.endswith(f".{allowed}") for allowed in allowed_hosts)


def _is_public_ip(ip_str: str) -> bool:
    ip_obj = ipaddress.ip_address(ip_str)
    return not (
        ip_obj.is_private
        or ip_obj.is_loopback
        or ip_obj.is_link_local
        or ip_obj.is_multicast
        or ip_obj.is_unspecified
        or ip_obj.is_reserved
    )


def validate_safe_http_url(raw_url: str, allowed_hosts: Optional[set[str]] = None) -> str:
    parsed = urlparse((raw_url or "").strip())
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("Only http/https URLs are allowed.")
    if not parsed.hostname:
        raise ValueError("URL must include a hostname.")
    hostname = parsed.hostname.strip(".")
    if allowed_hosts and not _host_matches_allowed(hostname, allowed_hosts):
        raise ValueError(f"URL host '{hostname}' is not allowed.")

    try:
        addr_info = socket.getaddrinfo(hostname, parsed.port or (443 if parsed.scheme == "https" else 80), type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise ValueError(f"Could not resolve host '{hostname}'.") from exc
    resolved_ips = {str(info[4][0]) for info in addr_info if info and info[4]}
    if not resolved_ips:
        raise ValueError(f"No IP addresses resolved for host '{hostname}'.")
    for ip in resolved_ips:
        if not _is_public_ip(ip):
            raise ValueError("Refusing to access non-public/private network URLs.")

    return parsed.geturl()


def fetch_text_url(
    raw_url: str,
    max_bytes: int = MAX_REMOTE_TEXT_BYTES,
    timeout_s: int = 20,
    allowed_hosts: Optional[set[str]] = None,
    allowed_content_types: Optional[tuple[str, ...]] = None,
) -> str:
    safe_url = validate_safe_http_url(raw_url, allowed_hosts=allowed_hosts)
    req = Request(safe_url, headers={"User-Agent": USER_AGENT})
    with urlopen(req, timeout=timeout_s) as response:
        content_type = str(response.headers.get("Content-Type", "")).lower()
        if allowed_content_types and not any(token in content_type for token in allowed_content_types):
            raise ValueError(f"Unexpected content type: {content_type or 'unknown'}")
        content_length = response.headers.get("Content-Length")
        if content_length and int(content_length) > max_bytes:
            raise ValueError("Remote response is too large.")

        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = response.read(65536)
            if not chunk:
                break
            total += len(chunk)
            if total > max_bytes:
                raise ValueError("Remote response exceeded max allowed size.")
            chunks.append(chunk)
    return b"".join(chunks).decode("utf-8", errors="ignore")


def estimate_generation_seconds(total_chars: int, engine_name: str) -> int:
    # Rough estimates for progress preview.
    cps = 28 if "edge" in engine_name else 16
    return int(total_chars / max(cps, 1))


@dataclass
class TTSResult:
    audio_path: str
    duration_seconds: float
    sample_rate: int


class TTSEngine(ABC):
    @abstractmethod
    async def generate(
        self,
        text: str,
        voice: str,
        speed: float = 1.0,
        output_path: Optional[str] = None,
    ) -> TTSResult:
        raise NotImplementedError

    @abstractmethod
    def list_voices(self) -> list[dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    def preview(self, voice: str) -> TTSResult:
        raise NotImplementedError

    @property
    @abstractmethod
    def max_concurrent(self) -> int:
        raise NotImplementedError

    @property
    @abstractmethod
    def requires_internet(self) -> bool:
        raise NotImplementedError


def run_coro_sync(coro: Any) -> Any:
    try:
        return asyncio.run(coro)
    except RuntimeError:
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()


class EdgeTTSEngine(TTSEngine):
    @property
    def max_concurrent(self) -> int:
        return 12

    @property
    def requires_internet(self) -> bool:
        return True

    def list_voices(self) -> list[dict[str, Any]]:
        try:
            import edge_tts  # type: ignore

            voices = run_coro_sync(edge_tts.list_voices())
            formatted = [{"name": v.get("ShortName", ""), "locale": v.get("Locale", "")} for v in voices]
            return [v for v in formatted if v["name"]]
        except Exception:
            return [
                {"name": "en-US-GuyNeural", "locale": "en-US"},
                {"name": "en-US-JennyNeural", "locale": "en-US"},
                {"name": "en-GB-RyanNeural", "locale": "en-GB"},
            ]

    async def generate(
        self,
        text: str,
        voice: str,
        speed: float = 1.0,
        output_path: Optional[str] = None,
    ) -> TTSResult:
        output_path = output_path or str(TEMP_DIR / f"edge_{int(time.time()*1000)}.mp3")
        rate_str = f"{int((speed - 1.0) * 100):+d}%"
        try:
            import edge_tts  # type: ignore

            communicate = edge_tts.Communicate(text=text, voice=voice, rate=rate_str)
            await communicate.save(output_path)
            duration = get_duration_ffprobe(output_path)
            return TTSResult(audio_path=output_path, duration_seconds=duration, sample_rate=24000)
        except Exception as exc:
            raise RuntimeError(f"edge-tts generation failed: {exc}") from exc

    def preview(self, voice: str) -> TTSResult:
        sample = PREVIEW_SAMPLE_TEXT
        preview_path = str(TEMP_DIR / f"preview_edge_{slugify(voice)}.mp3")
        return run_coro_sync(self.generate(sample, voice, output_path=preview_path))


class KokoroEngine(TTSEngine):
    def __init__(self) -> None:
        self._model: Any = None
        self._model_error: Optional[str] = None

    def _ensure_model(self) -> None:
        if self._model is not None or self._model_error is not None:
            return
        try:
            from kokoro_onnx import Kokoro  # type: ignore

            model_path = os.environ.get("KOKORO_MODEL", "kokoro-v1.0.onnx")
            voices_path = os.environ.get("KOKORO_VOICES", "voices-v1.0.bin")
            self._model = Kokoro(model_path, voices_path)
        except Exception as exc:
            self._model_error = str(exc)

    @property
    def max_concurrent(self) -> int:
        return 1

    @property
    def requires_internet(self) -> bool:
        return False

    def list_voices(self) -> list[dict[str, Any]]:
        # Keep it usable without model downloads.
        return [
            {"name": "af_sarah", "locale": "en-US"},
            {"name": "am_michael", "locale": "en-US"},
            {"name": "bf_emma", "locale": "en-GB"},
        ]

    def _mock_generate_wav(self, text: str, output_path: str) -> TTSResult:
        # Fallback keeps pipeline testable if kokoro/soundfile missing.
        sample_rate = 24000
        duration = max(1.0, min(8.0, len(text) / 55.0))
        frames = int(sample_rate * duration)
        output_path = str(Path(output_path).with_suffix(".wav"))
        with contextlib.closing(wave.open(output_path, "wb")) as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            silence_frame = (0).to_bytes(2, byteorder="little", signed=True)
            wf.writeframes(silence_frame * frames)
        return TTSResult(audio_path=output_path, duration_seconds=duration, sample_rate=sample_rate)

    async def generate(
        self,
        text: str,
        voice: str,
        speed: float = 1.0,
        output_path: Optional[str] = None,
    ) -> TTSResult:
        output_path = output_path or str(TEMP_DIR / f"kokoro_{int(time.time()*1000)}.wav")
        self._ensure_model()
        if self._model is None:
            return self._mock_generate_wav(text=text, output_path=output_path)

        try:
            import soundfile as sf  # type: ignore

            samples, sample_rate = self._model.create(text, voice=voice, speed=speed)
            sf.write(output_path, samples, sample_rate)
            duration = float(len(samples)) / float(sample_rate or 1)
            return TTSResult(audio_path=output_path, duration_seconds=duration, sample_rate=int(sample_rate))
        except Exception:
            return self._mock_generate_wav(text=text, output_path=output_path)

    def preview(self, voice: str) -> TTSResult:
        sample = PREVIEW_SAMPLE_TEXT
        preview_path = str(TEMP_DIR / f"preview_kokoro_{slugify(voice)}.wav")
        return run_coro_sync(self.generate(sample, voice, output_path=preview_path))


def create_tts_engine(engine_name: str) -> TTSEngine:
    if "kokoro" in engine_name.lower():
        return KokoroEngine()
    return EdgeTTSEngine()


class AudioCache:
    def __init__(self, cache_dir: str | Path = CACHE_DIR, max_size_mb: int = 500):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.max_size_bytes = max_size_mb * 1024 * 1024
        self.index_path = self.cache_dir / "cache_index.json"
        self.lock_path = self.cache_dir / ".cache_index.lock"
        self.index = self._load_index()
        self.repair_index()

    def _load_index(self) -> dict[str, dict[str, Any]]:
        with advisory_file_lock(self.lock_path):
            if not self.index_path.exists():
                return {}
            try:
                with open(self.index_path, "r", encoding="utf-8") as f:
                    payload = json.load(f)
                return payload if isinstance(payload, dict) else {}
            except Exception:
                backup = self.index_path.with_suffix(".json.bak")
                if backup.exists():
                    with open(backup, "r", encoding="utf-8") as f:
                        payload = json.load(f)
                    return payload if isinstance(payload, dict) else {}
                return {}

    def _save_index(self) -> None:
        with advisory_file_lock(self.lock_path):
            atomic_json_write(self.index_path, self.index, keep_backup=True)

    def _make_key(
        self,
        text: str,
        voice: str,
        engine: str,
        speed: float,
        pronunciation_hash: str = "",
        speed_mode: str = "native",
    ) -> str:
        effective_speed = speed if speed_mode == "native" else 1.0
        material = f"v={CACHE_KEY_SCHEMA_VERSION}|{text}|{voice}|{engine}|{effective_speed}|{pronunciation_hash}|{speed_mode}"
        return hashlib.md5(material.encode("utf-8")).hexdigest()

    def _is_cache_entry_valid(self, path: Path, entry: dict[str, Any]) -> bool:
        if not path.exists() or path.stat().st_size <= 0:
            return False
        expected_duration = float(entry.get("duration", 0.0) or 0.0)
        actual_duration = get_duration_ffprobe(str(path))
        if actual_duration <= 0:
            return False
        if expected_duration > 0 and abs(actual_duration - expected_duration) > 0.75:
            return False
        expected_sha = str(entry.get("sha256", "") or "")
        if expected_sha:
            with contextlib.suppress(Exception):
                if file_sha256(path) != expected_sha:
                    return False
        return True

    def get(
        self,
        text: str,
        voice: str,
        engine: str,
        speed: float = 1.0,
        pronunciation_hash: str = "",
        speed_mode: str = "native",
    ) -> Optional[str]:
        key = self._make_key(text, voice, engine, speed, pronunciation_hash=pronunciation_hash, speed_mode=speed_mode)
        entry = self.index.get(key)
        if not entry:
            return None
        path = self.cache_dir / entry.get("filename", "")
        if not self._is_cache_entry_valid(path, entry):
            self.index.pop(key, None)
            self._save_index()
            return None
        entry["last_accessed"] = time.time()
        self._save_index()
        return str(path)

    def put(
        self,
        text: str,
        voice: str,
        engine: str,
        speed: float,
        audio_path: str,
        duration: float,
        pronunciation_hash: str = "",
        speed_mode: str = "native",
    ) -> str:
        key = self._make_key(text, voice, engine, speed, pronunciation_hash=pronunciation_hash, speed_mode=speed_mode)
        ext = Path(audio_path).suffix or ".mp3"
        cache_filename = f"{key}{ext}"
        cache_path = self.cache_dir / cache_filename
        if Path(audio_path).resolve() != cache_path.resolve():
            shutil.copy2(audio_path, cache_path)
        size = cache_path.stat().st_size if cache_path.exists() else 0
        sha = file_sha256(cache_path) if cache_path.exists() else ""
        self.index[key] = {
            "filename": cache_filename,
            "voice": voice,
            "engine": engine,
            "duration": float(duration),
            "size_bytes": size,
            "sha256": sha,
            "key_schema_version": CACHE_KEY_SCHEMA_VERSION,
            "pronunciation_hash": pronunciation_hash,
            "speed_mode": speed_mode,
            "created": time.time(),
            "last_accessed": time.time(),
        }
        self._save_index()
        self._enforce_size_limit()
        return str(cache_path)

    def _enforce_size_limit(self) -> None:
        total_size = sum(v.get("size_bytes", 0) for v in self.index.values())
        if total_size <= self.max_size_bytes:
            return
        keys = sorted(self.index.keys(), key=lambda k: self.index[k].get("last_accessed", 0))
        while total_size > self.max_size_bytes and keys:
            key = keys.pop(0)
            entry = self.index.get(key, {})
            path = self.cache_dir / entry.get("filename", "")
            if path.exists():
                total_size -= int(entry.get("size_bytes", 0))
                with contextlib.suppress(Exception):
                    path.unlink()
            self.index.pop(key, None)
        self._save_index()

    def get_stats_for_manifest(self, manifest: dict[str, Any]) -> dict[str, dict[str, int]]:
        stats: dict[str, dict[str, int]] = {}
        for chapter in manifest.get("chapters", []):
            total = len(chapter.get("segments", []))
            cached = sum(1 for seg in chapter.get("segments", []) if seg.get("status") == "cached")
            stats[chapter.get("title", f"Chapter {chapter.get('index', 0)+1}")] = {
                "total": total,
                "cached": cached,
                "percent": round((cached / total) * 100) if total else 0,
            }
        return stats

    def repair_index(self) -> dict[str, int]:
        removed_stale = 0
        seen_files: set[str] = set()
        for key in list(self.index.keys()):
            entry = self.index.get(key, {})
            filename = str(entry.get("filename", "") or "")
            if not filename:
                self.index.pop(key, None)
                removed_stale += 1
                continue
            seen_files.add(filename)
            path = self.cache_dir / filename
            if not self._is_cache_entry_valid(path, entry):
                with contextlib.suppress(Exception):
                    if path.exists():
                        path.unlink()
                self.index.pop(key, None)
                removed_stale += 1

        orphaned = 0
        for file_path in self.cache_dir.iterdir():
            if not file_path.is_file():
                continue
            if file_path.name in ("cache_index.json", "cache_index.json.bak", ".cache_index.lock"):
                continue
            if file_path.name not in seen_files:
                orphaned += 1
                # Keep unknown files, but mark metadata so users can clean manually.
        self._save_index()
        return {"removed_stale": removed_stale, "orphaned_files": orphaned}


class PronunciationDict:
    def __init__(self, overrides: Optional[dict[str, str]] = None):
        self.overrides = overrides or {}

    def apply(self, text: str) -> str:
        output = text
        for word, replacement in self.overrides.items():
            pattern = re.compile(r"\b" + re.escape(word) + r"\b", re.IGNORECASE)
            output = pattern.sub(replacement, output)
        return output

    def save(self, path: str | Path) -> None:
        atomic_json_write(Path(path), self.overrides)

    @classmethod
    def load(cls, path: str | Path) -> "PronunciationDict":
        with open(path, "r", encoding="utf-8") as f:
            return cls(json.load(f))


SPEECH_VERBS = (
    r"said|asked|whispered|shouted|replied|muttered|called|cried|exclaimed|murmured|"
    r"growled|snapped|hissed|sighed|laughed|yelled|screamed|pleaded|demanded|insisted|"
    r"warned|added|continued|began|interrupted|suggested|agreed|admitted|explained|"
    r"announced|declared|protested|argued|offered|promised|answered|urged|begged"
)
PATTERN_POST = re.compile(
    r'["\u201C\u201D]([^"\u201C\u201D]+)["\u201C\u201D]\s*([A-Z][a-z]+(?:\s[A-Z][a-z]+)?)\s+('
    + SPEECH_VERBS
    + r")",
    re.MULTILINE,
)
PATTERN_PRE = re.compile(
    r'([A-Z][a-z]+(?:\s[A-Z][a-z]+)?)\s+('
    + SPEECH_VERBS
    + r')\s*,?\s*["\u201C\u201D]([^"\u201C\u201D]+)["\u201C\u201D]',
    re.MULTILINE,
)
PATTERN_MID = re.compile(
    r'["\u201C\u201D]([^"\u201C\u201D]+)["\u201C\u201D]\s*([A-Z][a-z]+(?:\s[A-Z][a-z]+)?)\s+('
    + SPEECH_VERBS
    + r')\s*,?\s*["\u201C\u201D]([^"\u201C\u201D]+)["\u201C\u201D]',
    re.MULTILINE,
)


def deduplicate_by_position(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    items = sorted(items, key=lambda x: (x["start"], -(x["end"] - x["start"])))
    output: list[dict[str, Any]] = []
    for item in items:
        overlap = False
        for existing in output:
            if not (item["end"] <= existing["start"] or item["start"] >= existing["end"]):
                overlap = True
                break
        if not overlap:
            output.append(item)
    return output


def extract_dialogue_regex(text: str) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for match in PATTERN_POST.finditer(text):
        results.append(
            {
                "start": match.start(),
                "end": match.end(),
                "dialogue": match.group(1).strip(),
                "speaker": match.group(2).strip(),
                "method": "regex",
            }
        )
    for match in PATTERN_PRE.finditer(text):
        results.append(
            {
                "start": match.start(),
                "end": match.end(),
                "dialogue": match.group(3).strip(),
                "speaker": match.group(1).strip(),
                "method": "regex",
            }
        )
    for match in PATTERN_MID.finditer(text):
        speaker = match.group(2).strip()
        first = match.group(1).strip()
        second = match.group(4).strip()
        results.append(
            {
                "start": match.start(),
                "end": match.end(),
                "dialogue": f"{first} ... {second}",
                "speaker": speaker,
                "method": "regex",
            }
        )
    return deduplicate_by_position(results)


def find_all_quotes(text: str) -> list[dict[str, Any]]:
    quote_pattern = re.compile(r'["\u201C](.+?)["\u201D]', re.DOTALL)
    quotes = []
    for match in quote_pattern.finditer(text):
        quotes.append(
            {
                "start": match.start(),
                "end": match.end(),
                "dialogue": match.group(1).strip(),
                "speaker": None,
                "method": "quote",
            }
        )
    return quotes


class SpacyAttributor:
    def __init__(self) -> None:
        self._nlp: Any = None
        self._attempted = False

    def _ensure_loaded(self) -> bool:
        if self._nlp is not None:
            return True
        if self._attempted:
            return False
        self._attempted = True
        try:
            import spacy  # type: ignore

            self._nlp = spacy.load("en_core_web_sm")
            return True
        except Exception:
            return False

    def attribute_unmatched(self, text: str, dialogue_start: int, dialogue_end: int) -> Optional[str]:
        if not self._ensure_loaded():
            return None
        ctx_start = max(0, dialogue_start - 500)
        ctx_end = min(len(text), dialogue_end + 500)
        context = text[ctx_start:ctx_end]
        doc = self._nlp(context)
        persons = [ent for ent in doc.ents if ent.label_ == "PERSON"]
        if not persons:
            return None
        dialogue_pos = dialogue_start - ctx_start
        closest = min(persons, key=lambda ent: abs(ent.start_char - dialogue_pos))
        return str(closest.text).strip()


class AlternationTracker:
    def __init__(self) -> None:
        self.last_two_speakers: list[str] = []

    def record(self, speaker: str) -> None:
        self.last_two_speakers.insert(0, speaker)
        self.last_two_speakers = self.last_two_speakers[:2]

    def predict_next(self) -> Optional[str]:
        if len(self.last_two_speakers) == 2 and self.last_two_speakers[0] != self.last_two_speakers[1]:
            return self.last_two_speakers[1]
        return None

    def reset(self) -> None:
        self.last_two_speakers = []


def detect_all_dialogue(chapter_text: str) -> list[dict[str, Any]]:
    tracker = AlternationTracker()
    spacy_attr = SpacyAttributor()

    quotes = find_all_quotes(chapter_text)
    regex_results = extract_dialogue_regex(chapter_text)

    for q in quotes:
        for r in regex_results:
            if not (q["end"] <= r["start"] or q["start"] >= r["end"]):
                q["speaker"] = r.get("speaker")
                q["method"] = "regex"
                break
        if q.get("speaker"):
            tracker.record(str(q["speaker"]))
            continue
        spacy_speaker = spacy_attr.attribute_unmatched(chapter_text, q["start"], q["end"])
        if spacy_speaker:
            q["speaker"] = spacy_speaker
            q["method"] = "spacy"
            tracker.record(spacy_speaker)
            continue
        predicted = tracker.predict_next()
        if predicted:
            q["speaker"] = predicted
            q["method"] = "alternation"
            tracker.record(predicted)
        else:
            q["speaker"] = None
            q["method"] = "unattributed"

    return quotes


CHAPTER_PATTERNS = [
    re.compile(
        r"^(?:CHAPTER|Chapter)\s+(?:\d+|[IVXLCDM]+|[A-Z][a-z]+(?:\s[A-Z][a-z]+)?)(?:\s*[:.\-—]\s*.+)?$",
        re.MULTILINE,
    ),
    re.compile(r"^(?:PART|Part)\s+(?:\d+|[IVXLCDM]+|[A-Z][a-z]+)", re.MULTILINE),
    re.compile(r"^\s*\d{1,3}\.?\s*$", re.MULTILINE),
    re.compile(r"^([A-Z][A-Z\s]{2,58})$(?=\s*\n\s*\n)", re.MULTILINE),
    re.compile(r"^([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,8})\s*$(?=\s*\n\s*\n)", re.MULTILINE),
]


def detect_chapters_pattern(text: str) -> list[dict[str, Any]]:
    chapters: list[dict[str, Any]] = []
    for pattern in CHAPTER_PATTERNS:
        for match in pattern.finditer(text):
            chapters.append({"position": match.start(), "title": match.group(0).strip(), "method": "pattern"})
    chapters.sort(key=lambda x: x["position"])
    deduped: list[dict[str, Any]] = []
    min_gap = 200
    for chapter in chapters:
        if deduped and abs(chapter["position"] - deduped[-1]["position"]) < min_gap:
            continue
        deduped.append(chapter)
    return deduped


SCENE_BREAK_PATTERNS = [
    re.compile(r"^\s*\*\s*\*\s*\*\s*$", re.MULTILINE),
    re.compile(r"^\s*\*{3,}\s*$", re.MULTILINE),
    re.compile(r"^\s*-{3,}\s*$", re.MULTILINE),
    re.compile(r"^\s*~{3,}\s*$", re.MULTILINE),
    re.compile(r"^\s*#\s*$", re.MULTILINE),
    re.compile(r"\n{3,}", re.MULTILINE),
]


def detect_scene_breaks(text: str) -> list[int]:
    positions: list[int] = []
    for pattern in SCENE_BREAK_PATTERNS:
        positions.extend(match.start() for match in pattern.finditer(text))
    return sorted(set(positions))


def split_text_into_chapters(text: str) -> list[dict[str, str]]:
    markers = detect_chapters_pattern(text)
    if len(markers) < 2:
        return [{"title": "Chapter 1", "text": text.strip()}]
    output: list[dict[str, str]] = []
    for i, marker in enumerate(markers):
        start = marker["position"]
        end = markers[i + 1]["position"] if i + 1 < len(markers) else len(text)
        chunk = text[start:end].strip()
        if chunk:
            output.append({"title": marker["title"], "text": chunk})
    return output or [{"title": "Chapter 1", "text": text.strip()}]


def split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z\"“])", text.strip())
    return [p.strip() for p in parts if p.strip()]


def chunk_text(text: str, max_chars: int = 5500) -> list[str]:
    if len(text) <= max_chars:
        return [text.strip()]
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0
    for sentence in split_sentences(text):
        sent_len = len(sentence) + 1
        if current and current_len + sent_len > max_chars:
            chunks.append(" ".join(current).strip())
            current = [sentence]
            current_len = sent_len
        else:
            current.append(sentence)
            current_len += sent_len
    if current:
        chunks.append(" ".join(current).strip())
    return chunks


def extract_text_from_url(url: str) -> str:
    safe_url = validate_safe_http_url(url)
    html = fetch_text_url(
        safe_url,
        max_bytes=MAX_REMOTE_TEXT_BYTES,
        timeout_s=20,
        allowed_content_types=("text/", "application/xhtml+xml", "application/xml"),
    )
    try:
        import trafilatura  # type: ignore

        extracted = trafilatura.extract(html, include_comments=False, include_tables=False)
        return extracted or ""
    except Exception:
        # Lightweight HTML cleanup fallback.
        html = re.sub(r"(?is)<script.*?>.*?</script>", " ", html)
        html = re.sub(r"(?is)<style.*?>.*?</style>", " ", html)
        text = re.sub(r"(?s)<[^>]+>", " ", html)
        return re.sub(r"\s+", " ", text).strip()


def extract_chapters_from_epub(epub_path: str) -> tuple[list[dict[str, str]], dict[str, str]]:
    try:
        import ebooklib  # type: ignore
        from bs4 import BeautifulSoup  # type: ignore
        from ebooklib import epub  # type: ignore
    except Exception as exc:
        raise RuntimeError(f"EPUB support requires ebooklib + beautifulsoup4: {exc}") from exc

    book = epub.read_epub(epub_path)
    title = (book.get_metadata("DC", "title") or [["Untitled", None]])[0][0]
    author = (book.get_metadata("DC", "creator") or [["Unknown", None]])[0][0]
    chapters: list[dict[str, str]] = []
    idx = 1
    for item in book.get_items_of_type(ebooklib.ITEM_DOCUMENT):
        soup = BeautifulSoup(item.get_content(), "html.parser")
        heading = soup.find(["h1", "h2", "h3"])
        chapter_title = heading.get_text(strip=True) if heading else f"Chapter {idx}"
        text = soup.get_text(separator="\n").strip()
        if len(text) < 80:
            continue
        chapters.append({"title": chapter_title, "text": text})
        idx += 1
        del soup, text
        gc.collect()
    if not chapters:
        chapters = [{"title": "Chapter 1", "text": ""}]
    return chapters, {"title": title or "Untitled", "author": author or "Unknown"}


def detect_chapters_pdf_fonts(pdf_path: str) -> list[dict[str, Any]]:
    try:
        import pdfplumber  # type: ignore
    except Exception:
        return []
    chapters: list[dict[str, Any]] = []
    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages):
            chars = page.chars or []
            if not chars:
                continue
            # Basic line clustering by "top" rounded to nearest 2 pixels.
            lines: dict[int, list[dict[str, Any]]] = {}
            for ch in chars:
                key = int(round(float(ch.get("top", 0.0)) / 2.0))
                lines.setdefault(key, []).append(ch)
            for line_chars in lines.values():
                line_text = "".join(c.get("text", "") for c in sorted(line_chars, key=lambda x: x.get("x0", 0.0))).strip()
                if not line_text:
                    continue
                avg_size = sum(float(c.get("size", 0.0)) for c in line_chars) / max(len(line_chars), 1)
                if avg_size > 14 and len(line_text) < 80:
                    chapters.append(
                        {
                            "position": page_num,
                            "title": line_text,
                            "font_size": avg_size,
                            "method": "font_size",
                        }
                    )
    return chapters


def extract_chapters_from_pdf(pdf_path: str) -> tuple[list[dict[str, str]], dict[str, str]]:
    try:
        import pdfplumber  # type: ignore
    except Exception as exc:
        raise RuntimeError(f"PDF support requires pdfplumber: {exc}") from exc

    chapters: list[dict[str, str]] = []
    font_markers = detect_chapters_pdf_fonts(pdf_path)
    break_pages = sorted({m["position"] for m in font_markers})
    break_set = set(break_pages)
    buffer: list[str] = []
    chapter_idx = 1
    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages):
            text = (page.extract_text() or "").strip()
            if page_num in break_set and buffer:
                chapter_text = "\n".join(buffer).strip()
                title = next((m["title"] for m in font_markers if m["position"] == page_num), f"Chapter {chapter_idx}")
                chapters.append({"title": title, "text": chapter_text})
                chapter_idx += 1
                buffer = []
                gc.collect()
            if text:
                buffer.append(text)
        if buffer:
            chapters.append({"title": f"Chapter {chapter_idx}", "text": "\n".join(buffer).strip()})
    if not chapters:
        chapters = [{"title": "Chapter 1", "text": ""}]
    return chapters, {"title": Path(pdf_path).stem, "author": "Unknown"}


def extract_source_chapters(
    input_path: Optional[str] = None,
    url: Optional[str] = None,
    raw_text: Optional[str] = None,
) -> tuple[list[dict[str, str]], dict[str, str], str, str]:
    if raw_text and raw_text.strip():
        chapters = split_text_into_chapters(raw_text.strip())
        return chapters, {"title": "Pasted Text", "author": "Unknown"}, "inline_text", "text"

    if url and url.strip():
        text = extract_text_from_url(url.strip())
        chapters = split_text_into_chapters(text)
        host = urlparse(url).netloc or "url"
        return chapters, {"title": f"Web Import - {host}", "author": "Unknown"}, url, "url"

    if not input_path:
        raise ValueError("No input provided. Upload a file, enter a URL, or paste text.")
    path = Path(input_path)
    ext = path.suffix.lower()
    if ext == ".epub":
        chapters, meta = extract_chapters_from_epub(str(path))
        return chapters, meta, str(path), "epub"
    if ext == ".pdf":
        chapters, meta = extract_chapters_from_pdf(str(path))
        return chapters, meta, str(path), "pdf"
    if ext == ".txt":
        text = path.read_text(encoding="utf-8", errors="ignore")
        chapters = split_text_into_chapters(text)
        return chapters, {"title": path.stem, "author": "Unknown"}, str(path), "txt"
    text = path.read_text(encoding="utf-8", errors="ignore")
    chapters = split_text_into_chapters(text)
    return chapters, {"title": path.stem, "author": "Unknown"}, str(path), "text"


def run_preflight_checks() -> list[list[str]]:
    checks: list[list[str]] = []
    checks.append(["FFmpeg", "OK" if shutil.which("ffmpeg") else "Missing", "Required for assembly"])
    checks.append(["FFprobe", "OK" if shutil.which("ffprobe") else "Missing", "Required for duration/validation"])
    checks.append(["edge-tts", "OK" if _module_exists("edge_tts") else "Optional", "Cloud TTS engine"])
    checks.append(["kokoro-onnx", "OK" if _module_exists("kokoro_onnx") else "Optional", "Offline TTS engine"])
    checks.append(["spacy", "OK" if _module_exists("spacy") else "Optional", "Dialogue attribution fallback"])
    checks.append(["spacy model", "OK" if _spacy_model_exists() else "Optional", "en_core_web_sm"])
    disk_mb = shutil.disk_usage(str(BASE_DIR)).free // (1024 * 1024)
    checks.append(["Free disk", "OK" if disk_mb > 1024 else "Low", f"{disk_mb} MB available"])
    checks.append(["Free cloud memory", "OK", "JSONBlob anonymous manifest backup is supported"])
    return checks


def _module_exists(module_name: str) -> bool:
    try:
        __import__(module_name)
        return True
    except Exception:
        return False


def _spacy_model_exists() -> bool:
    try:
        import spacy  # type: ignore

        spacy.load("en_core_web_sm")
        return True
    except Exception:
        return False


def upload_manifest_to_free_cloud(manifest: dict[str, Any]) -> str:
    data = json.dumps(manifest, ensure_ascii=False).encode("utf-8")
    req = Request(
        "https://jsonblob.com/api/jsonBlob",
        data=data,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    with urlopen(req, timeout=20) as response:
        location = response.headers.get("Location", "")
    if not location:
        raise RuntimeError("Cloud backup failed: missing location header.")
    if location.startswith("/"):
        return f"https://jsonblob.com{location}"
    return location


def load_manifest_from_free_cloud(url: str) -> dict[str, Any]:
    payload = fetch_text_url(
        url.strip(),
        max_bytes=MAX_CLOUD_MANIFEST_BYTES,
        timeout_s=20,
        allowed_hosts={"jsonblob.com"},
        allowed_content_types=("application/json", "text/plain"),
    )
    data = json.loads(payload)
    if not isinstance(data, dict):
        raise RuntimeError("Cloud manifest payload is not a JSON object.")
    return ensure_manifest_defaults(data)


def infer_speaker_for_span(
    span_start: int,
    span_end: int,
    segment_text: str,
    dialogues: list[dict[str, Any]],
    tracker: AlternationTracker,
) -> str:
    has_quotes = bool(re.search(r'["\u201C\u201D]', segment_text))
    overlaps = [
        d for d in dialogues if not (span_end <= int(d["start"]) or span_start >= int(d["end"])) and d.get("speaker")
    ]
    if overlaps:
        speaker = str(overlaps[0]["speaker"]).strip()
        tracker.record(speaker)
        return speaker
    if has_quotes:
        predicted = tracker.predict_next()
        if predicted:
            tracker.record(predicted)
            return predicted
    return "narrator"


def update_run_state(
    manifest: dict[str, Any],
    state: str,
    message: str = "",
    manifest_path: Optional[str] = None,
) -> None:
    runtime = manifest.setdefault("runtime", {})
    runtime["state"] = state
    runtime["message"] = message
    runtime["updated_at"] = now_iso()
    if manifest_path:
        save_manifest(manifest, manifest_path)


def ensure_manifest_defaults(manifest: dict[str, Any]) -> dict[str, Any]:
    manifest.setdefault("settings", {})
    manifest.setdefault("book", {})
    manifest.setdefault("chapters", [])
    progress = manifest.setdefault("progress", {})
    progress.setdefault("generation_started", None)
    progress.setdefault("estimated_remaining_seconds", 0)
    runtime = manifest.setdefault("runtime", {})
    runtime.setdefault("state", "idle")
    runtime.setdefault("message", "")
    runtime.setdefault("updated_at", now_iso())
    runtime.setdefault(
        "assembly",
        {
            "concat_done": False,
            "music_mixed": False,
            "speed_adjusted": False,
            "normalized": False,
            "output_done": False,
        },
    )
    runtime.setdefault("cloud_backup", {"enabled": False, "url": ""})

    total_segments = 0
    completed_segments = 0
    for c_idx, chapter in enumerate(manifest.get("chapters", [])):
        chapter.setdefault("index", c_idx)
        chapter.setdefault("title", f"Chapter {c_idx + 1}")
        chapter.setdefault("segments", [])
        for s_idx, seg in enumerate(chapter.get("segments", [])):
            seg.setdefault("index", s_idx)
            seg.setdefault("speaker", "narrator")
            seg.setdefault("voice", manifest["settings"].get("narrator_voice", "en-US-GuyNeural"))
            seg.setdefault("status", "pending")
            seg.setdefault("cache_file", None)
            seg.setdefault("duration_seconds", None)
            total_segments += 1
            if seg.get("status") == "cached":
                completed_segments += 1
        chapter["status"] = "complete" if all(seg.get("status") == "cached" for seg in chapter.get("segments", [])) else "pending"
    progress.setdefault("total_segments", total_segments)
    progress.setdefault("completed_segments", completed_segments)
    progress.setdefault("last_completed_chapter", -1)
    progress.setdefault("last_completed_segment", -1)
    return manifest


def build_manifest(settings: dict[str, Any], chapters: list[dict[str, Any]], book: dict[str, Any]) -> dict[str, Any]:
    total_segments = sum(len(ch.get("segments", [])) for ch in chapters)
    completed_segments = sum(
        1 for ch in chapters for seg in ch.get("segments", []) if seg.get("status") == "cached"
    )
    return {
        "version": APP_VERSION,
        "book": book,
        "settings": settings,
        "chapters": chapters,
        "progress": {
            "total_segments": total_segments,
            "completed_segments": completed_segments,
            "last_completed_chapter": -1,
            "last_completed_segment": -1,
            "generation_started": None,
            "estimated_remaining_seconds": 0,
        },
        "runtime": {
            "state": "idle",
            "message": "",
            "updated_at": now_iso(),
            "assembly": {
                "concat_done": False,
                "music_mixed": False,
                "speed_adjusted": False,
                "normalized": False,
                "output_done": False,
            },
            "cloud_backup": {"enabled": False, "url": ""},
        },
    }


def stage_parse(
    input_path: Optional[str] = None,
    settings: Optional[dict[str, Any]] = None,
    url: Optional[str] = None,
    raw_text: Optional[str] = None,
) -> tuple[dict[str, Any], str]:
    ensure_runtime_dirs()
    settings = dict(settings or {})
    engine_name = settings.get("tts_engine", "edge-tts")
    narrator_voice = settings.get("narrator_voice", "en-US-GuyNeural")
    dialogue_voice = settings.get("dialogue_voice", "en-US-JennyNeural")
    speed = float(settings.get("speed_multiplier", 1.0))
    speed_mode = str(settings.get("speed_mode", "native"))
    settings.setdefault("character_voices", {})
    settings.setdefault("pronunciation_overrides", {})
    settings.setdefault("background_music", None)
    settings.setdefault("music_duck_db", -15)
    settings.setdefault("output_format", "m4b")
    settings.setdefault("speed_mode", speed_mode)
    settings.setdefault("max_queue_size", 32)
    settings.setdefault("cache_max_size_mb", 500)
    settings.setdefault("enable_free_cloud_memory", False)
    settings.setdefault("free_cloud_manifest_url", "")
    settings.setdefault("cache_key_schema_version", CACHE_KEY_SCHEMA_VERSION)

    source_chapters, meta, source_ref, source_type = extract_source_chapters(input_path, url, raw_text)
    first_chunk_text = ""
    for chapter in source_chapters:
        candidate = str(chapter.get("text", "") or "").strip()
        if candidate:
            first_chunk_text = candidate[:2000]
            break
    source_content_sig = hashlib.md5(first_chunk_text.encode("utf-8")).hexdigest()[:10] if first_chunk_text else "empty"
    cache = AudioCache(max_size_mb=int(settings.get("cache_max_size_mb", 500)))
    pronunciation_hash = hash_dict(settings.get("pronunciation_overrides", {}))

    manifest_chapters: list[dict[str, Any]] = []
    character_occurrences: dict[str, int] = {}
    total_chars = 0

    for chapter_idx, chapter_info in enumerate(source_chapters):
        chapter_title = chapter_info.get("title") or f"Chapter {chapter_idx+1}"
        chapter_text = chapter_info.get("text", "").strip()
        if not chapter_text:
            continue
        total_chars += len(chapter_text)
        dialogues = detect_all_dialogue(chapter_text)
        tracker = AlternationTracker()
        scene_break_positions = set(detect_scene_breaks(chapter_text))
        chapter_segments: list[dict[str, Any]] = []

        para_matches = list(re.finditer(r"(.*?)(?:\n\s*\n|$)", chapter_text, flags=re.DOTALL))
        for para_match in para_matches:
            para_text = para_match.group(1).strip()
            if not para_text:
                continue
            start = para_match.start(1)

            if re.fullmatch(r"(\*{3,}|-\-{3,}|~{3,}|#)", para_text.strip()):
                tracker.reset()
                if chapter_segments:
                    chapter_segments[-1]["scene_break_after"] = True
                continue

            chunks = chunk_text(para_text, max_chars=5500)
            cursor = 0
            for chunk_idx, chunk in enumerate(chunks):
                rel = para_text.find(chunk, cursor)
                if rel < 0:
                    rel = cursor
                abs_start = start + rel
                abs_end = abs_start + len(chunk)
                cursor = rel + len(chunk)

                speaker = infer_speaker_for_span(abs_start, abs_end, chunk, dialogues, tracker)
                if speaker != "narrator":
                    character_occurrences[speaker] = character_occurrences.get(speaker, 0) + 1

                voice_map = settings.get("character_voices", {})
                if speaker != "narrator":
                    selected = voice_map.get(speaker, {"voice": dialogue_voice, "detected_by": "auto"})
                    voice = selected.get("voice", dialogue_voice)
                    voice_map.setdefault(speaker, {"voice": voice, "detected_by": "auto"})
                else:
                    voice = narrator_voice

                text_hash = hashlib.md5(f"{chunk}|{voice}|{engine_name}|{speed}".encode("utf-8")).hexdigest()
                cached_file = cache.get(
                    chunk,
                    voice,
                    engine_name,
                    speed=speed,
                    pronunciation_hash=pronunciation_hash,
                    speed_mode=speed_mode,
                )
                status = "cached" if cached_file else "pending"
                duration = get_duration_ffprobe(cached_file) if cached_file else None
                scene_after = any(abs(p - abs_end) < 4 for p in scene_break_positions)
                chapter_segments.append(
                    {
                        "index": len(chapter_segments),
                        "text": chunk,
                        "text_hash": text_hash,
                        "speaker": speaker,
                        "voice": voice,
                        "cache_file": cached_file,
                        "duration_seconds": duration,
                        "status": status,
                        "paragraph_break_after": chunk_idx == len(chunks) - 1,
                        "scene_break_after": scene_after,
                    }
                )

        manifest_chapters.append(
            {
                "index": chapter_idx,
                "title": chapter_title,
                "status": "complete" if all(s.get("status") == "cached" for s in chapter_segments) else "pending",
                "segments": chapter_segments,
            }
        )
        del chapter_text, dialogues, chapter_segments
        gc.collect()

    settings["character_voices"] = settings.get("character_voices", {})
    book_title = meta.get("title") or "Untitled"
    book_author = meta.get("author") or "Unknown"
    book_key = make_book_profile_key({"title": book_title, "author": book_author, "source_type": source_type})
    profile = load_book_profile(book_key)
    profile_character_voices = profile.get("character_voices", {}) if isinstance(profile.get("character_voices", {}), dict) else {}
    profile_pron = profile.get("pronunciation_overrides", {}) if isinstance(profile.get("pronunciation_overrides", {}), dict) else {}
    merged_character_voices = dict(profile_character_voices)
    merged_character_voices.update(settings.get("character_voices", {}))
    merged_pron = dict(profile_pron)
    merged_pron.update(settings.get("pronunciation_overrides", {}))
    settings["character_voices"] = merged_character_voices
    settings["pronunciation_overrides"] = merged_pron
    manifest = build_manifest(
        settings=settings,
        chapters=manifest_chapters,
        book={
            "title": book_title,
            "author": book_author,
            "source_file": source_ref,
            "source_type": source_type,
        },
    )
    apply_character_voices_to_segments(manifest, merged_character_voices)
    post_merge_pron_hash = hash_dict(merged_pron)
    for chapter in manifest.get("chapters", []):
        for segment in chapter.get("segments", []):
            text = str(segment.get("text", "") or "")
            voice = str(segment.get("voice", settings.get("narrator_voice", "en-US-GuyNeural")) or settings.get("narrator_voice", "en-US-GuyNeural"))
            text_hash = hashlib.md5(f"{text}|{voice}|{engine_name}|{speed}".encode("utf-8")).hexdigest()
            segment["text_hash"] = text_hash
            cached_file = cache.get(
                text,
                voice,
                engine_name,
                speed=speed,
                pronunciation_hash=post_merge_pron_hash,
                speed_mode=speed_mode,
            )
            if cached_file:
                segment["status"] = "cached"
                segment["cache_file"] = cached_file
                segment["duration_seconds"] = get_duration_ffprobe(cached_file)
            else:
                segment["status"] = "pending"
                segment["cache_file"] = None
                segment["duration_seconds"] = None
        chapter["status"] = "complete" if all(seg.get("status") == "cached" for seg in chapter.get("segments", [])) else "pending"

    manifest["progress"]["estimated_remaining_seconds"] = estimate_generation_seconds(total_chars, engine_name)
    manifest["progress"]["total_segments"] = sum(len(ch.get("segments", [])) for ch in manifest.get("chapters", []))
    manifest["progress"]["completed_segments"] = sum(
        1 for ch in manifest.get("chapters", []) for seg in ch.get("segments", []) if seg.get("status") == "cached"
    )
    manifest["character_occurrences"] = character_occurrences
    manifest["runtime"]["cloud_backup"]["enabled"] = bool(settings.get("enable_free_cloud_memory", False))
    manifest["runtime"]["cloud_backup"]["url"] = str(settings.get("free_cloud_manifest_url", "") or "")
    source_fingerprint = hashlib.md5(
        f"{source_type}|{source_ref}|{book_title}|{book_author}|{total_chars}|{source_content_sig}".encode("utf-8")
    ).hexdigest()[:12]
    manifest["runtime"]["project_id"] = f"{slugify(book_title)}_{source_fingerprint}"
    manifest["runtime"]["source_fingerprint"] = source_fingerprint
    manifest["runtime"]["book_profile_key"] = book_key

    manifest_name = f"{slugify(book_title)}_{source_fingerprint}_manifest.json"
    manifest_path = str(MANIFESTS_DIR / manifest_name)
    update_run_state(manifest, "parsed", "Parse completed", manifest_path=None)
    save_manifest(manifest, manifest_path)
    return manifest, manifest_path


async def stage_generate(
    manifest: dict[str, Any],
    manifest_path: Optional[str] = None,
    cancel_event: Optional[threading.Event] = None,
    progress_callback: Optional[Callable[[int, int, str], None]] = None,
) -> dict[str, Any]:
    ensure_runtime_dirs()
    manifest = ensure_manifest_defaults(manifest)
    settings = manifest.get("settings", {})
    engine_name = settings.get("tts_engine", "edge-tts")
    engine = create_tts_engine(engine_name)
    cache = AudioCache(max_size_mb=int(settings.get("cache_max_size_mb", 500)))
    pronunciation = PronunciationDict(settings.get("pronunciation_overrides", {}))
    speed = float(settings.get("speed_multiplier", 1.0))
    speed_mode = str(settings.get("speed_mode", "native"))
    pronunciation_hash = hash_dict(settings.get("pronunciation_overrides", {}))
    max_queue_size = max(4, int(settings.get("max_queue_size", 32)))
    max_workers = min(engine.max_concurrent, max(1, int(settings.get("max_concurrent", engine.max_concurrent))))

    pending: list[tuple[int, int]] = []
    for c_idx, chapter in enumerate(manifest.get("chapters", [])):
        for s_idx, segment in enumerate(chapter.get("segments", [])):
            if segment.get("status") == "cached":
                cache_file = str(segment.get("cache_file", "") or "")
                if not cache_file or not Path(cache_file).exists():
                    segment["status"] = "pending"
                    segment["cache_file"] = None
                    segment["duration_seconds"] = None
                    pending.append((c_idx, s_idx))
            else:
                pending.append((c_idx, s_idx))

    total = len(pending)
    done = 0
    manifest["progress"]["generation_started"] = manifest["progress"].get("generation_started") or now_iso()
    update_run_state(manifest, "generating", "Generating segment audio", manifest_path)

    if total == 0:
        if progress_callback:
            progress_callback(1, 1, "All segments already cached.")
        update_run_state(manifest, "generated", "All segments already cached", manifest_path)
        return manifest

    lock = asyncio.Lock()
    queue: asyncio.Queue[Optional[tuple[int, int]]] = asyncio.Queue(maxsize=max_queue_size)

    async def process_one(ch_idx: int, seg_idx: int) -> None:
        nonlocal done
        if cancel_event and cancel_event.is_set():
            return
        chapter = manifest["chapters"][ch_idx]
        segment = chapter["segments"][seg_idx]
        text = segment.get("text", "")
        speaker = segment.get("speaker", "narrator")
        voice = segment.get("voice") or settings.get("narrator_voice", "en-US-GuyNeural")
        transformed_text = pronunciation.apply(text)
        tts_speed = speed if speed_mode == "native" else 1.0
        try:
            cached = cache.get(
                transformed_text,
                voice,
                engine_name,
                speed=tts_speed,
                pronunciation_hash=pronunciation_hash,
                speed_mode=speed_mode,
            )
            if cached:
                duration = get_duration_ffprobe(cached)
                async with lock:
                    segment["cache_file"] = cached
                    segment["duration_seconds"] = duration
                    segment["status"] = "cached"
            else:
                ext = ".mp3" if "edge" in engine_name.lower() else ".wav"
                tmp_path = str(TEMP_DIR / f"gen_{ch_idx}_{seg_idx}_{uuid.uuid4().hex}{ext}")
                if cancel_event and cancel_event.is_set():
                    return
                result = await engine.generate(
                    text=transformed_text,
                    voice=voice,
                    speed=tts_speed,
                    output_path=tmp_path,
                )
                cache_path = cache.put(
                    transformed_text,
                    voice,
                    engine_name,
                    speed=tts_speed,
                    audio_path=result.audio_path,
                    duration=result.duration_seconds,
                    pronunciation_hash=pronunciation_hash,
                    speed_mode=speed_mode,
                )
                duration = result.duration_seconds or get_duration_ffprobe(cache_path)
                async with lock:
                    segment["cache_file"] = cache_path
                    segment["duration_seconds"] = duration
                    segment["status"] = "cached"
                    segment["speed_mode"] = speed_mode
                    segment["speed_applied"] = speed if speed_mode != "native" else tts_speed

            async with lock:
                done += 1
                manifest["progress"]["completed_segments"] = sum(
                    1
                    for chap in manifest["chapters"]
                    for seg in chap["segments"]
                    if seg.get("status") == "cached"
                )
                manifest["progress"]["last_completed_chapter"] = ch_idx
                manifest["progress"]["last_completed_segment"] = seg_idx
                chapter["status"] = "complete" if all(s.get("status") == "cached" for s in chapter["segments"]) else "pending"
                if manifest_path:
                    save_manifest(manifest, manifest_path)
                if progress_callback:
                    progress_callback(done, total, f"Generated chapter {ch_idx+1}, segment {seg_idx+1} ({speaker})")
        except Exception as exc:
            async with lock:
                segment["status"] = "error"
                segment["error"] = str(exc)
                done += 1
                if manifest_path:
                    save_manifest(manifest, manifest_path)
                if progress_callback:
                    progress_callback(done, total, f"Error on chapter {ch_idx+1}, segment {seg_idx+1}: {exc}")

    async def producer() -> None:
        for item in pending:
            if cancel_event and cancel_event.is_set():
                break
            await queue.put(item)
        for _ in range(max_workers):
            await queue.put(None)

    async def worker() -> None:
        while True:
            item = await queue.get()
            if item is None:
                queue.task_done()
                break
            ch_idx, seg_idx = item
            await process_one(ch_idx, seg_idx)
            queue.task_done()

    producer_task = asyncio.create_task(producer())
    workers = [asyncio.create_task(worker()) for _ in range(max_workers)]
    await asyncio.gather(producer_task)
    await queue.join()
    await asyncio.gather(*workers)

    manifest["progress"]["completed_segments"] = sum(
        1 for chapter in manifest["chapters"] for seg in chapter["segments"] if seg.get("status") == "cached"
    )
    if manifest_path:
        save_manifest(manifest, manifest_path)
    if cancel_event and cancel_event.is_set():
        update_run_state(manifest, "cancelled", "Generation cancelled by user", manifest_path)
    elif any(seg.get("status") == "error" for ch in manifest["chapters"] for seg in ch["segments"]):
        update_run_state(manifest, "failed", "Generation completed with errors", manifest_path)
    else:
        update_run_state(manifest, "generated", "All segments generated", manifest_path)
    return manifest


def normalize_loudness(input_path: str, output_path: str, target_lufs: float = -19.0) -> str:
    if not ffmpeg_exists():
        raise RuntimeError("FFmpeg/ffprobe are required for loudness normalization.")
    cmd1 = [
        "ffmpeg",
        "-hide_banner",
        "-i",
        input_path,
        "-af",
        f"loudnorm=I={target_lufs}:TP=-1.5:LRA=11:print_format=json",
        "-f",
        "null",
        "-",
    ]
    pass1 = subprocess.run(cmd1, capture_output=True, text=True, check=False, timeout=DEFAULT_FFMPEG_TIMEOUT_S)
    stats_match = re.search(r"\{[\s\S]*?\}", pass1.stderr)
    if not stats_match:
        raise RuntimeError("Failed to parse loudnorm pass 1 metrics from ffmpeg output.")
    stats = json.loads(stats_match.group(0))
    af = (
        f"loudnorm=I={target_lufs}:TP=-1.5:LRA=11"
        f":measured_I={stats['input_i']}"
        f":measured_TP={stats['input_tp']}"
        f":measured_LRA={stats['input_lra']}"
        f":measured_thresh={stats['input_thresh']}"
        f":offset={stats['target_offset']}:linear=true"
    )
    cmd2 = [
        "ffmpeg",
        "-hide_banner",
        "-i",
        input_path,
        "-af",
        af,
        "-ar",
        "44100",
        "-ac",
        "1",
        "-y",
        output_path,
    ]
    run_ffmpeg(cmd2)
    return output_path


def generate_chapter_metadata(manifest: dict[str, Any], output_path: str) -> None:
    lines = [";FFMETADATA1"]
    lines.append(f"title={manifest['book'].get('title', 'Untitled')}")
    lines.append(f"artist={manifest['book'].get('author', 'Unknown')}")
    lines.append(f"album={manifest['book'].get('title', 'Untitled')}")
    lines.append("genre=Audiobook")
    lines.append("")
    current_time_ms = 0
    for chapter in manifest.get("chapters", []):
        chapter_duration_ms = 0
        for seg in chapter.get("segments", []):
            chapter_duration_ms += int(float(seg.get("duration_seconds") or 0.0) * 1000)
            if seg.get("scene_break_after"):
                chapter_duration_ms += 1000
            elif seg.get("paragraph_break_after"):
                chapter_duration_ms += 500
            if seg.get("speaker") not in (None, "narrator"):
                chapter_duration_ms += 300
        chapter_duration_ms += 2000
        lines.append("[CHAPTER]")
        lines.append("TIMEBASE=1/1000")
        lines.append(f"START={current_time_ms}")
        lines.append(f"END={current_time_ms + chapter_duration_ms}")
        lines.append(f"title={chapter.get('title', f'Chapter {chapter.get('index', 0) + 1}')}")
        lines.append("")
        current_time_ms += chapter_duration_ms

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def create_silence_file(duration: float, output_path: Path) -> Path:
    if not ffmpeg_exists():
        # No ffmpeg; make a tiny WAV silence fallback.
        sample_rate = 24000
        frames = int(sample_rate * duration)
        with contextlib.closing(wave.open(str(output_path.with_suffix(".wav")), "wb")) as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            silence_frame = (0).to_bytes(2, byteorder="little", signed=True)
            wf.writeframes(silence_frame * frames)
        return output_path.with_suffix(".wav")

    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-f",
        "lavfi",
        "-i",
        "anullsrc=r=24000:cl=mono",
        "-t",
        str(duration),
        "-q:a",
        "0",
        "-y",
        str(output_path),
    ]
    run_ffmpeg(cmd)
    return output_path


def build_atempo_filter(speed: float) -> str:
    if speed <= 0:
        raise ValueError("Speed multiplier must be > 0")
    factors: list[float] = []
    remaining = float(speed)
    while remaining > 2.0:
        factors.append(2.0)
        remaining /= 2.0
    while remaining < 0.5:
        factors.append(0.5)
        remaining /= 0.5
    if abs(remaining - 1.0) > 0.0001:
        factors.append(remaining)
    if not factors:
        return "anull"
    return ",".join(f"atempo={f:.6f}".rstrip("0").rstrip(".") for f in factors)


def stage_assemble(
    manifest: dict[str, Any],
    output_format: str = "m4b",
    normalize_audio: bool = True,
    manifest_path: Optional[str] = None,
    cancel_event: Optional[threading.Event] = None,
) -> str:
    ensure_runtime_dirs()
    if not ffmpeg_exists():
        raise RuntimeError("FFmpeg and ffprobe are required for assembly stage.")
    update_run_state(manifest, "assembling", "Starting assembly", manifest_path)

    chapter_gap = create_silence_file(2.0, TEMP_DIR / "silence_2s.mp3")
    scene_gap = create_silence_file(1.0, TEMP_DIR / "silence_1s.mp3")
    para_gap = create_silence_file(0.5, TEMP_DIR / "silence_05s.mp3")
    dialogue_gap = create_silence_file(0.3, TEMP_DIR / "silence_03s.mp3")

    runtime = manifest.setdefault("runtime", {})
    assembly = runtime.setdefault(
        "assembly",
        {"concat_done": False, "music_mixed": False, "speed_adjusted": False, "normalized": False, "output_done": False},
    )

    def mark(stage_key: str, value: bool, message: str) -> None:
        assembly[stage_key] = value
        update_run_state(manifest, "assembling", message, manifest_path)

    def ensure_not_cancelled(phase: str) -> None:
        if cancel_event and cancel_event.is_set():
            update_run_state(manifest, "cancelled", f"Cancelled during assembly ({phase})", manifest_path)
            raise RuntimeError(f"Assembly cancelled during {phase}.")

    concat_list = TEMP_DIR / "concat_list.txt"
    with open(concat_list, "w", encoding="utf-8") as f:
        for c_idx, chapter in enumerate(manifest.get("chapters", [])):
            for segment in chapter.get("segments", []):
                seg_path = segment.get("cache_file")
                if not seg_path or not Path(seg_path).exists():
                    raise RuntimeError(f"Missing segment audio file for chapter {c_idx+1}, segment {segment.get('index')}")
                f.write(f"file '{Path(seg_path).resolve().as_posix()}'\n")
                if segment.get("speaker") not in (None, "narrator"):
                    f.write(f"file '{dialogue_gap.resolve().as_posix()}'\n")
                if segment.get("scene_break_after"):
                    f.write(f"file '{scene_gap.resolve().as_posix()}'\n")
                elif segment.get("paragraph_break_after"):
                    f.write(f"file '{para_gap.resolve().as_posix()}'\n")
            if c_idx < len(manifest.get("chapters", [])) - 1:
                f.write(f"file '{chapter_gap.resolve().as_posix()}'\n")

    concatenated = TEMP_DIR / "concatenated.mp3"
    ensure_not_cancelled("concat")
    if not (assembly.get("concat_done") and concatenated.exists()):
        run_ffmpeg(
            [
                "ffmpeg",
                "-hide_banner",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(concat_list),
                "-ac",
                "1",
                "-ar",
                "44100",
                "-c:a",
                "libmp3lame",
                "-q:a",
                "2",
                "-y",
                str(concatenated),
            ]
        )
        mark("concat_done", True, "Concat complete")

    assembled_path = concatenated

    settings = manifest.get("settings", {})
    bg_music = settings.get("background_music")
    if bg_music:
        mixed = TEMP_DIR / "mixed.mp3"
        duck_db = settings.get("music_duck_db", -15)
        ensure_not_cancelled("music_mix")
        if not (assembly.get("music_mixed") and mixed.exists()):
            run_ffmpeg(
                [
                    "ffmpeg",
                    "-hide_banner",
                    "-i",
                    str(assembled_path),
                    "-i",
                    str(bg_music),
                    "-filter_complex",
                    f"[1:a]volume={duck_db}dB[music];[0:a][music]amix=inputs=2:duration=first:dropout_transition=3",
                    "-ac",
                    "1",
                    "-ar",
                    "44100",
                    "-y",
                    str(mixed),
                ]
            )
            mark("music_mixed", True, "Background music mixed")
        assembled_path = mixed
    else:
        assembly["music_mixed"] = True

    speed_mode = str(settings.get("speed_mode", "native"))
    speed = float(settings.get("speed_multiplier", 1.0))
    if speed_mode != "native" and abs(speed - 1.0) > 0.0001:
        speed_out = TEMP_DIR / "speed_adjusted.mp3"
        ensure_not_cancelled("speed_adjust")
        if not (assembly.get("speed_adjusted") and speed_out.exists()):
            run_ffmpeg(
                [
                    "ffmpeg",
                    "-hide_banner",
                    "-i",
                    str(assembled_path),
                    "-filter:a",
                    build_atempo_filter(speed),
                    "-ac",
                    "1",
                    "-ar",
                    "44100",
                    "-y",
                    str(speed_out),
                ]
            )
            mark("speed_adjusted", True, "Speed post-processing complete")
        assembled_path = speed_out
    else:
        assembly["speed_adjusted"] = True

    if normalize_audio:
        normalized = TEMP_DIR / "normalized.mp3"
        ensure_not_cancelled("normalize")
        if not (assembly.get("normalized") and normalized.exists()):
            assembled_path = Path(normalize_loudness(str(assembled_path), str(normalized)))
            mark("normalized", True, "Loudness normalization complete")
        else:
            assembled_path = normalized
    else:
        assembly["normalized"] = True

    book_title = slugify(manifest.get("book", {}).get("title", "Audiobook"), fallback="audiobook")
    ensure_not_cancelled("final_output")
    if output_format.lower() == "m4b":
        metadata_file = TEMP_DIR / "chapters_meta.txt"
        generate_chapter_metadata(manifest, str(metadata_file))
        output_path = OUTPUT_DIR / f"{book_title}.m4b"
        run_ffmpeg(
            [
                "ffmpeg",
                "-hide_banner",
                "-i",
                str(assembled_path),
                "-i",
                str(metadata_file),
                "-map",
                "0:a",
                "-map_metadata",
                "1",
                "-c:a",
                "aac",
                "-b:a",
                "64k",
                "-ar",
                "44100",
                "-ac",
                "1",
                "-y",
                str(output_path),
            ]
        )
    else:
        output_path = OUTPUT_DIR / f"{book_title}.mp3"
        shutil.copy2(assembled_path, output_path)

    mark("output_done", True, f"Output ready: {output_path.name}")
    update_run_state(manifest, "completed", "Assembly completed", manifest_path)
    return str(output_path)


def build_chapter_table(manifest: dict[str, Any]) -> list[list[Any]]:
    rows: list[list[Any]] = []
    for chapter in manifest.get("chapters", []):
        segments = chapter.get("segments", [])
        chars = {
            seg.get("speaker")
            for seg in segments
            if seg.get("speaker") not in (None, "", "narrator")
        }
        total = len(segments)
        cached = sum(1 for seg in segments if seg.get("status") == "cached")
        rows.append([chapter.get("title"), total, len(chars), f"{cached}/{total}"])
    return rows


def build_character_table(manifest: dict[str, Any]) -> list[list[Any]]:
    rows: list[list[Any]] = []
    character_voices = manifest.get("settings", {}).get("character_voices", {})
    occurrences = manifest.get("character_occurrences", {})
    for character, info in sorted(character_voices.items()):
        rows.append([character, info.get("voice", ""), info.get("detected_by", "auto"), occurrences.get(character, 0)])
    return rows


def build_chapter_progress(manifest: dict[str, Any]) -> list[list[Any]]:
    rows: list[list[Any]] = []
    for chapter in manifest.get("chapters", []):
        segs = chapter.get("segments", [])
        done = sum(1 for seg in segs if seg.get("status") == "cached")
        rows.append([chapter.get("title"), chapter.get("status", "pending"), f"{done}/{len(segs)}"])
    return rows


def manifest_has_generation_errors(manifest: dict[str, Any]) -> bool:
    for chapter in manifest.get("chapters", []):
        for segment in chapter.get("segments", []):
            if segment.get("status") == "error":
                return True
            if segment.get("status") == "cached":
                cache_file = str(segment.get("cache_file", "") or "")
                if not cache_file or not Path(cache_file).exists():
                    return True
            elif not segment.get("cache_file"):
                return True
    return False


def rows_to_markdown(headers: list[str], rows: list[list[Any]]) -> str:
    if not rows:
        return "_No data yet._"
    head = "| " + " | ".join(headers) + " |"
    sep = "|" + "|".join(["---"] * len(headers)) + "|"
    body = ["| " + " | ".join(str(cell) for cell in row) + " |" for row in rows]
    return "\n".join([head, sep] + body)


def format_eta(seconds: float) -> str:
    seconds = max(0, int(seconds))
    minutes, secs = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def runtime_state_badge(state: str, detail: str = "") -> str:
    state_norm = (state or "idle").lower()
    palette = {
        "idle": ("⚪", "Idle"),
        "parsed": ("🔵", "Parsed"),
        "generating": ("🟣", "Generating"),
        "generated": ("🟢", "Generated"),
        "assembling": ("🟠", "Assembling"),
        "cancel_requested": ("🟡", "Cancel Requested"),
        "cancelled": ("🟡", "Cancelled"),
        "failed": ("🔴", "Failed"),
        "completed": ("✅", "Completed"),
    }
    icon, label = palette.get(state_norm, ("⚪", state_norm.title()))
    if detail:
        return f"{icon} **{label}** · {detail}"
    return f"{icon} **{label}**"


def build_chapter_preview_markdown(manifest: dict[str, Any], max_items: int = 8) -> str:
    chapters = manifest.get("chapters", []) or []
    if not chapters:
        return "_No chapter preview available._"
    lines = ["### Live Chapter Preview"]
    for chapter in chapters[:max_items]:
        title = str(chapter.get("title", f"Chapter {chapter.get('index', 0) + 1}"))
        segments = chapter.get("segments", []) or []
        snippet = ""
        if segments:
            snippet = str(segments[0].get("text", "")).strip().replace("\n", " ")
        if len(snippet) > 160:
            snippet = snippet[:157] + "..."
        seg_count = len(segments)
        lines.append(f"- **{title}** ({seg_count} segments)")
        if snippet:
            lines.append(f"  - _{snippet}_")
    if len(chapters) > max_items:
        lines.append(f"- _...and {len(chapters) - max_items} more chapters._")
    return "\n".join(lines)


def parse_pronunciation_table(rows: Any) -> dict[str, str]:
    overrides: dict[str, str] = {}
    if not rows:
        return overrides
    for row in rows:
        if not row or len(row) < 2:
            continue
        word = str(row[0]).strip()
        sounds_like = str(row[1]).strip()
        if word and sounds_like:
            overrides[word] = sounds_like
    return overrides


def normalize_engine_label(label: str) -> str:
    low = (label or "").lower()
    if "kokoro" in low:
        return "kokoro"
    return "edge-tts"


def normalize_speed_mode_label(label: str) -> str:
    low = (label or "").lower()
    if "post-process" in low:
        return "post_process"
    return "native"


def voices_for_engine(engine_label: str) -> list[str]:
    engine = create_tts_engine(normalize_engine_label(engine_label))
    voices = [v.get("name", "") for v in engine.list_voices()]
    return [v for v in voices if v]


def voice_catalog_for_engine(engine_label: str) -> list[dict[str, str]]:
    engine = create_tts_engine(normalize_engine_label(engine_label))
    catalog: list[dict[str, str]] = []
    for item in engine.list_voices():
        name = str(item.get("name", "") or "").strip()
        if not name:
            continue
        locale = str(item.get("locale", "") or "").strip()
        catalog.append({"name": name, "locale": locale})
    if not catalog:
        fallback = voices_for_engine(engine_label)
        catalog = [{"name": voice, "locale": ""} for voice in fallback]
    catalog.sort(key=lambda item: (item.get("locale", ""), item.get("name", "")))
    return catalog


def _voice_browser_pager_updates(catalog: list[dict[str, str]], page_idx: int, gr_module: Any) -> tuple[Any, ...]:
    total = len(catalog)
    total_pages = max(1, (total + VOICE_BROWSER_PAGE_SIZE - 1) // VOICE_BROWSER_PAGE_SIZE)
    safe_page = max(0, min(page_idx, total_pages - 1))
    start = safe_page * VOICE_BROWSER_PAGE_SIZE
    items = catalog[start : start + VOICE_BROWSER_PAGE_SIZE]
    page_label = f"Voice page {safe_page + 1}/{total_pages} · {total} voices"
    prev_interactive = safe_page > 0
    next_interactive = safe_page < total_pages - 1

    row_updates: list[Any] = []
    for idx in range(VOICE_BROWSER_PAGE_SIZE):
        if idx < len(items):
            voice_name = items[idx]["name"]
            locale = items[idx].get("locale", "")
            label = f"**{voice_name}**"
            if locale:
                label += f"  \n`{locale}`"
            row_updates.extend(
                [
                    gr_module.Markdown(value=label, visible=True),
                    gr_module.Textbox(value=voice_name, visible=False),
                    gr_module.Button(visible=True, interactive=True),
                ]
            )
        else:
            row_updates.extend(
                [
                    gr_module.Markdown(value="", visible=False),
                    gr_module.Textbox(value="", visible=False),
                    gr_module.Button(visible=False, interactive=False),
                ]
            )
    return (
        safe_page,
        gr_module.Markdown(value=page_label),
        gr_module.Button(interactive=prev_interactive),
        gr_module.Button(interactive=next_interactive),
        *row_updates,
    )


def resolve_source_inputs(
    input_mode: str,
    file_obj: Any,
    url: str,
    text: str,
    fallback_file_path: str = "",
) -> tuple[Optional[str], str, str]:
    mode = (input_mode or "file").lower()
    file_path = getattr(file_obj, "name", None) if file_obj else None
    url_value = (url or "").strip()
    text_value = (text or "").strip()
    if "url" in mode:
        return None, url_value, ""
    if "text" in mode or "paste" in mode:
        return None, "", text_value
    return (file_path or existing_path_or_empty(fallback_file_path) or None), "", ""


def collect_project_inventory() -> dict[str, dict[str, str]]:
    inventory: dict[str, dict[str, str]] = {}
    cloud_urls: set[str] = set()
    known_output_paths: set[str] = set()
    for manifest_file in sorted(MANIFESTS_DIR.glob("*.json")):
        if manifest_file.name.endswith(".bak"):
            continue
        try:
            manifest = load_manifest(manifest_file)
        except Exception:
            continue
        title = str(manifest.get("book", {}).get("title", manifest_file.stem) or manifest_file.stem)
        state = str(manifest.get("runtime", {}).get("state", "unknown") or "unknown")
        slug = slugify(title, fallback=manifest_file.stem)
        output_path = ""
        for ext in ("m4b", "mp3"):
            candidate = OUTPUT_DIR / f"{slug}.{ext}"
            if candidate.exists():
                output_path = str(candidate)
                known_output_paths.add(output_path)
                break
        cloud_url = str(manifest.get("runtime", {}).get("cloud_backup", {}).get("url", "") or "")
        if cloud_url:
            cloud_urls.add(cloud_url)
        key = f"local::{manifest_file}"
        inventory[key] = {
            "id": key,
            "label": f"{title} · {state} · local",
            "title": title,
            "state": state,
            "manifest_path": str(manifest_file),
            "cloud_url": cloud_url,
            "output_path": output_path,
            "storage": "local",
        }

    for cloud_url in sorted(cloud_urls):
        key = f"cloud::{cloud_url}"
        if key in inventory:
            continue
        inventory[key] = {
            "id": key,
            "label": f"{cloud_url[:44]}... · cloud",
            "title": "Cloud backup",
            "state": "cloud",
            "manifest_path": "",
            "cloud_url": cloud_url,
            "output_path": "",
            "storage": "cloud",
        }
    last_cloud = str(load_app_state().get("last_cloud_url", "") or "")
    if last_cloud:
        key = f"cloud::{last_cloud}"
        inventory.setdefault(
            key,
            {
                "id": key,
                "label": f"{last_cloud[:44]}... · cloud",
                "title": "Cloud backup",
                "state": "cloud",
                "manifest_path": "",
                "cloud_url": last_cloud,
                "output_path": "",
                "storage": "cloud",
            },
        )
    for output_file in sorted(OUTPUT_DIR.glob("*")):
        if output_file.suffix.lower() not in {".mp3", ".m4b"}:
            continue
        output_path = str(output_file)
        if output_path in known_output_paths:
            continue
        key = f"output::{output_path}"
        inventory[key] = {
            "id": key,
            "label": f"{output_file.name} · output",
            "title": output_file.stem,
            "state": "ready",
            "manifest_path": "",
            "cloud_url": "",
            "output_path": output_path,
            "storage": "output",
        }
    return inventory


def project_meta_to_markdown(meta: Optional[dict[str, str]]) -> str:
    if not meta:
        return "_No project selected._"
    lines = [
        f"**Title:** {meta.get('title', '-')}",
        f"**State:** {meta.get('state', '-')}",
        f"**Storage:** {meta.get('storage', '-')}",
    ]
    if meta.get("manifest_path"):
        lines.append(f"**Manifest:** `{meta['manifest_path']}`")
    if meta.get("output_path"):
        lines.append(f"**Output:** `{meta['output_path']}`")
    if meta.get("cloud_url"):
        lines.append(f"**Cloud URL:** `{meta['cloud_url']}`")
    return "\n\n".join(lines)


def apply_character_voices_to_segments(manifest: dict[str, Any], char_map: dict[str, dict[str, Any]]) -> None:
    settings = manifest.get("settings", {})
    narrator_voice = str(settings.get("narrator_voice", "en-US-GuyNeural") or "en-US-GuyNeural")
    dialogue_voice = str(settings.get("dialogue_voice", "en-US-JennyNeural") or "en-US-JennyNeural")
    for chapter in manifest.get("chapters", []):
        for segment in chapter.get("segments", []):
            speaker = str(segment.get("speaker", "narrator") or "narrator")
            old_voice = str(segment.get("voice", "") or "")
            if speaker in (None, "", "narrator"):
                new_voice = narrator_voice
            else:
                entry = char_map.get(speaker) or {"voice": dialogue_voice, "detected_by": "auto"}
                new_voice = str(entry.get("voice", dialogue_voice) or dialogue_voice)
            if old_voice and old_voice != new_voice:
                # Voice changed, cached clip is no longer valid.
                segment["status"] = "pending"
                segment["cache_file"] = None
                segment["duration_seconds"] = None
            segment["voice"] = new_voice


MOBILE_CSS = """
.gradio-container {
  max-width: 1100px !important;
  background: radial-gradient(circle at 20% 20%, rgba(99, 102, 241, 0.12), transparent 45%),
              radial-gradient(circle at 80% 10%, rgba(14, 165, 233, 0.12), transparent 35%),
              #0b1020;
}
.gr-button {min-height: 48px !important; font-size: 1rem !important; border-radius: 12px !important;}
input, textarea, select {font-size: 16px !important;}
.easy-action-btn button {
  min-height: 56px !important;
  font-size: 1.08rem !important;
  font-weight: 700 !important;
}
.bottom-mobile-nav {
  position: sticky;
  bottom: 10px;
  z-index: 30;
  padding: 8px;
  border-radius: 14px;
  background: rgba(15, 23, 42, 0.85);
  border: 1px solid rgba(148, 163, 184, 0.2);
  backdrop-filter: blur(8px);
}
.bottom-mobile-nav .nav-grid {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 6px;
}
.bottom-mobile-nav button {
  border-radius: 10px;
  border: 1px solid rgba(148, 163, 184, 0.2);
  padding: 8px 6px;
  font-size: 12px;
  background: rgba(30, 41, 59, 0.75);
  color: #e2e8f0;
  cursor: pointer;
  transition: all 0.2s ease;
  min-height: 44px;
}
.bottom-mobile-nav button:active,
.bottom-mobile-nav button:focus {
  background: rgba(99, 102, 241, 0.3);
  border-color: rgba(99, 102, 241, 0.6);
  color: #ffffff;
}
.glass-card {
  backdrop-filter: blur(10px);
  background: rgba(15, 23, 42, 0.58) !important;
  border: 1px solid rgba(148, 163, 184, 0.25) !important;
  border-radius: 16px !important;
  box-shadow: 0 10px 30px rgba(2, 6, 23, 0.35) !important;
}
/* Android-optimized mobile styles */
@media (max-width: 768px) {
  .gradio-container {padding: 10px 10px 100px 10px !important;}
  .gr-row {flex-direction: column !important; gap: 10px !important;}
  .gr-button {width: 100% !important;}
  /* Bottom navigation bar - Android thumb zone */
  .bottom-mobile-nav {
    position: fixed;
    bottom: 0;
    left: 0;
    right: 0;
    width: 100%;
    height: auto;
    border-radius: 0;
    padding: 8px;
    border-top: 1px solid rgba(148, 163, 184, 0.3);
    background: rgba(15, 23, 42, 0.98);
    z-index: 50;
  }
  .bottom-mobile-nav .nav-grid {
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 4px;
  }
  .bottom-mobile-nav button {
    padding: 12px 6px;
    font-size: 13px;
    min-height: 48px;
    font-weight: 500;
  }
  body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', sans-serif;
  }
  /* Prevent keyboard from hiding buttons */
  @supports (padding: max(0px)) {
    body {
      padding-bottom: max(0px, env(safe-area-inset-bottom));
    }
  }
}
"""


def build_ui():
    try:
        import gradio as gr  # type: ignore
    except Exception as exc:
        raise RuntimeError(f"Gradio is required for UI mode: {exc}") from exc

    ensure_runtime_dirs()
    cancel_event = threading.Event()
    theme = (
        gr.themes.Soft(
            primary_hue="indigo",
            secondary_hue="slate",
            neutral_hue="slate",
            radius_size=gr.themes.sizes.radius_lg,
            text_size=gr.themes.sizes.text_md,
        ).set(
            body_background_fill="#0b1020",
            block_background_fill="rgba(15, 23, 42, 0.55)",
            block_border_color="rgba(148, 163, 184, 0.22)",
            block_shadow="0 14px 35px rgba(2, 6, 23, 0.40)",
            panel_background_fill="rgba(15, 23, 42, 0.70)",
            input_background_fill="rgba(15, 23, 42, 0.65)",
            button_primary_background_fill="#4f46e5",
            button_primary_background_fill_hover="#6366f1",
            button_primary_text_color="#f8fafc",
        )
    )

    with gr.Blocks(title="Audiobook Creator V7", theme=theme, css=MOBILE_CSS) as app:
        manifest_path_state = gr.State("")
        cloud_url_state = gr.State("")
        project_map_state = gr.State({})
        voice_catalog_state = gr.State([])
        voice_page_state = gr.State(0)
        remembered_adv_file_state = gr.State("")
        remembered_quick_file_state = gr.State("")
        draft_saved_state = gr.State("")

        with gr.Sidebar(open=True):
            gr.Markdown("## My Projects")
            gr.Markdown("Load saved manifests from local disk or cloud backups.")
            project_selector = gr.Dropdown(label="Saved Projects", choices=[], value=None)
            project_details = gr.Markdown("_No project selected._")
            with gr.Row():
                refresh_projects_btn = gr.Button("Refresh", variant="secondary")
                load_project_btn = gr.Button("Load", variant="primary")
            resume_last_btn = gr.Button("Resume Last Project", variant="primary")
            open_output_btn = gr.Button("Open Output", variant="secondary")
            delete_project_btn = gr.Button("Delete Selected", variant="stop")
            project_action_status = gr.Markdown("")

        with gr.Tab("Easy Mobile Mode"):
            gr.Markdown("### 📱 Simple Audiobook Creation\nOne-tap workflow: Paste → Generate → Download")
            gr.HTML(
                """
                <div class="bottom-mobile-nav">
                  <div class="nav-grid">
                    <button type="button" onclick="window.__abmSwitchTab?.('Easy Mobile Mode')">Easy</button>
                    <button type="button" onclick="window.__abmSwitchTab?.('Input (Advanced)')">Input</button>
                    <button type="button" onclick="window.__abmSwitchTab?.('Voices')">Voices</button>
                    <button type="button" onclick="window.__abmSwitchTab?.('Generate')">Generate</button>
                    <button type="button" onclick="window.__abmSwitchTab?.('Player')">Player</button>
                  </div>
                </div>
                <script>
                window.__abmSwitchTab = function (name) {
                  const tabs = Array.from(document.querySelectorAll('[role="tab"]'));
                  const target = tabs.find((el) => (el.textContent || '').trim() === name);
                  if (target) target.click();
                };
                </script>
                """
            )

            # Main input area - large and prominent
            quick_text_input = gr.Textbox(
                label="📝 Paste your text here",
                lines=15,
                placeholder="Paste chapter text, article, or book excerpt...\n\nOr switch to File/URL mode below",
                visible=True,
            )

            # Progressive disclosure: Input mode selector
            with gr.Group():
                gr.Markdown("**Want to use a file or URL instead?**")
                quick_input_mode = gr.Radio(["Text (Recommended)", "File", "URL"], value="Text (Recommended)", label="Input mode")

            quick_file_input = gr.File(
                label="📁 Drag & drop book file (EPUB/PDF/TXT)",
                file_types=[".epub", ".pdf", ".txt"],
                visible=False,
            )
            quick_url_input = gr.Textbox(label="🔗 Book/article URL", placeholder="https://...", visible=False)

            # Simple format choice (hidden in advanced)
            quick_output_format = gr.Radio(["MP3 (recommended)", "M4B (with chapters)"], value="MP3 (recommended)", label="Output format")

            # Main action button
            quick_generate_btn = gr.Button("⚡ Generate Audiobook", variant="primary", elem_classes=["easy-action-btn"], scale=2)
            quick_cancel_btn = gr.Button("Cancel", variant="stop", elem_classes=["easy-action-btn"], scale=1)

            # Status display
            quick_state_badge = gr.Markdown(runtime_state_badge("idle", "Ready"))
            quick_status = gr.Markdown("")
            quick_draft_restore_md = gr.Markdown("")
            quick_chapter_preview_md = gr.Markdown("_No chapter preview yet._")

            # Results
            quick_player = gr.Audio(label="🎵 Listen to your audiobook", type="filepath")
            quick_download = gr.File(label="⬇️ Download")

            # Advanced options (hidden by default)
            with gr.Accordion("🔧 Advanced options (optional)", open=False):
                gr.Markdown("Only adjust these if you have special needs.")
                quick_free_cloud = gr.Checkbox(label="☁️ Save project to free cloud memory", value=True)
                quick_cloud_url = gr.Textbox(label="Cloud memory URL", interactive=False)

        with gr.Tab("Input (Advanced)"):
            input_mode = gr.Radio(["File", "URL", "Paste Text"], value="File", label="Input mode")
            file_input = gr.File(
                label="Drag & drop book file (EPUB/PDF/TXT)",
                file_types=[".epub", ".pdf", ".txt"],
                visible=True,
            )
            url_input = gr.Textbox(label="URL", placeholder="https://...", visible=False)
            text_input = gr.Textbox(label="Raw text", lines=8, visible=False)
            parse_btn = gr.Button("Parse & Build Manifest", variant="primary")
            parse_status = gr.Markdown("")
            draft_restore_info_md = gr.Markdown("")
            chapter_list_md = gr.Markdown("")
            chapter_preview_md = gr.Markdown("_No chapter preview yet._")
            time_estimate = gr.Markdown("")

        with gr.Tab("Voices"):
            engine_select = gr.Radio(
                ["edge-tts (Cloud, Free)", "kokoro (Offline, CPU)"],
                value="edge-tts (Cloud, Free)",
                label="TTS Engine",
            )
            with gr.Row():
                narrator_voice = gr.Dropdown(label="Narrator Voice", choices=voices_for_engine("edge-tts"), scale=2)
                narrator_preview = gr.Button("Preview Narrator", scale=1)
            narrator_audio = gr.Audio(label="Narrator Preview", visible=True)
            with gr.Row():
                dialogue_voice = gr.Dropdown(label="Dialogue Voice", choices=voices_for_engine("edge-tts"), scale=2)
                dialogue_preview = gr.Button("Preview Dialogue", scale=1)
            dialogue_audio = gr.Audio(label="Dialogue Preview", visible=True)
            gr.Markdown("### Voice Browser")
            gr.Markdown("Preview any listed voice with a dedicated button.")
            with gr.Row():
                voice_prev_page_btn = gr.Button("Previous", variant="secondary", scale=1)
                voice_page_label = gr.Markdown("Voice page 1/1 · 0 voices", scale=2)
                voice_next_page_btn = gr.Button("Next", variant="secondary", scale=1)
            voice_browser_labels: list[Any] = []
            voice_browser_values: list[Any] = []
            voice_browser_buttons: list[Any] = []
            for _ in range(VOICE_BROWSER_PAGE_SIZE):
                with gr.Row():
                    label = gr.Markdown(visible=False)
                    value = gr.Textbox(visible=False)
                    button = gr.Button("Preview 10s", visible=False)
                voice_browser_labels.append(label)
                voice_browser_values.append(value)
                voice_browser_buttons.append(button)
            voice_browser_audio = gr.Audio(label="Voice Browser Preview", visible=True)
            character_table = gr.Dataframe(
                headers=["Character", "Voice", "Detection Method", "Occurrences"],
                value=[],
                interactive=True,
            )
            pronunciation_table = gr.Dataframe(headers=["Word", "Sounds Like"], value=[], interactive=True)
            speed_slider = gr.Slider(0.8, 1.3, value=1.0, step=0.05, label="Speed")
            speed_mode = gr.Radio(
                ["native (separate cache per speed)", "post-process (cache-friendly)"],
                value="native (separate cache per speed)",
                label="Speed handling",
            )
            with gr.Accordion("Background music", open=False):
                music_file = gr.File(label="Music MP3", file_types=[".mp3"])
                music_volume = gr.Slider(-25, -5, value=-15, step=1, label="Music duck volume (dB)")

        with gr.Tab("Generate"):
            with gr.Row():
                generate_btn = gr.Button("Generate Audiobook", variant="primary", scale=2)
                cancel_btn = gr.Button("Cancel Generation", variant="stop", scale=1)
            output_format = gr.Radio(["M4B (Chaptered)", "MP3"], value="M4B (Chaptered)", label="Output Format")
            with gr.Accordion("Advanced generation options", open=False):
                normalize_check = gr.Checkbox(label="Normalize loudness (-19 LUFS)", value=True)
                low_memory_mode = gr.Checkbox(label="Low-memory mode (best for free cloud machines)", value=True)
                cache_size_mb = gr.Slider(128, 4096, value=500, step=64, label="Cache size limit (MB)")
                free_cloud_memory = gr.Checkbox(label="Enable free cloud memory backup (JSONBlob)", value=False)
            generation_badge = gr.Markdown(runtime_state_badge("idle", "Waiting to start"))
            progress_text = gr.Markdown("")
            chapter_progress_md = gr.Markdown("")

        with gr.Tab("Player"):
            audio_player = gr.Audio(label="Audiobook", type="filepath")
            download_file = gr.File(label="Download")

        with gr.Tab("System"):
            preflight_table = gr.Dataframe(headers=["Check", "Status", "Detail"], value=run_preflight_checks(), interactive=False)
            refresh_preflight_btn = gr.Button("Refresh system checks")
            cloud_manifest_url = gr.Textbox(label="Free cloud manifest URL", placeholder="https://jsonblob.com/api/jsonBlob/...")
            with gr.Row():
                backup_cloud_btn = gr.Button("Backup manifest to free cloud")
                restore_cloud_btn = gr.Button("Restore manifest from cloud URL")
            cloud_status = gr.Markdown("")

        def on_engine_change(engine_label: str):
            voice_choices = voices_for_engine(engine_label)
            default_n = voice_choices[0] if voice_choices else None
            default_d = voice_choices[1] if len(voice_choices) > 1 else default_n
            return (
                gr.Dropdown(choices=voice_choices, value=default_n),
                gr.Dropdown(choices=voice_choices, value=default_d),
            )

        def on_restore_ui_draft():
            draft = load_ui_draft()
            adv_mode = str(draft.get("adv_input_mode", "File") or "File")
            quick_mode = str(draft.get("quick_input_mode", "Paste Text") or "Paste Text")
            adv_file_path = existing_path_or_empty(str(draft.get("adv_file_path", "") or ""))
            quick_file_path = existing_path_or_empty(str(draft.get("quick_file_path", "") or ""))
            adv_msg = f"Remembered file: `{adv_file_path}`" if adv_file_path else ""
            quick_msg = f"Remembered file: `{quick_file_path}`" if quick_file_path else ""
            return (
                gr.Radio(value=adv_mode),
                gr.Textbox(value=str(draft.get("adv_url", "") or "")),
                gr.Textbox(value=str(draft.get("adv_text", "") or "")),
                gr.Radio(value=quick_mode),
                gr.Textbox(value=str(draft.get("quick_url", "") or "")),
                gr.Textbox(value=str(draft.get("quick_text", "") or "")),
                gr.Radio(value=str(draft.get("quick_output_format", "MP3") or "MP3")),
                gr.Checkbox(value=bool(draft.get("quick_free_cloud", True))),
                gr.Textbox(value=str(draft.get("cloud_manifest_url", "") or "")),
                adv_file_path,
                quick_file_path,
                adv_msg,
                quick_msg,
            )

        def on_save_ui_draft(
            adv_mode: str,
            adv_url: str,
            adv_text: str,
            quick_mode: str,
            quick_url: str,
            quick_text: str,
            quick_output_fmt: str,
            quick_free_cloud_val: bool,
            cloud_manifest_val: str,
            remembered_adv_file: str,
            remembered_quick_file: str,
        ):
            draft = load_ui_draft()
            draft["adv_input_mode"] = adv_mode
            draft["adv_url"] = adv_url
            draft["adv_text"] = adv_text
            draft["quick_input_mode"] = quick_mode
            draft["quick_url"] = quick_url
            draft["quick_text"] = quick_text
            draft["quick_output_format"] = quick_output_fmt
            draft["quick_free_cloud"] = bool(quick_free_cloud_val)
            draft["cloud_manifest_url"] = cloud_manifest_val
            draft["adv_file_path"] = existing_path_or_empty(remembered_adv_file)
            draft["quick_file_path"] = existing_path_or_empty(remembered_quick_file)
            save_ui_draft(draft)
            return now_iso()

        def on_adv_file_upload(file_obj: Any):
            remembered = copy_uploaded_input(file_obj, "advanced")
            draft = load_ui_draft()
            draft["adv_file_path"] = remembered
            save_ui_draft(draft)
            msg = f"Remembered file: `{remembered}`" if remembered else ""
            return remembered, msg

        def on_quick_file_upload(file_obj: Any):
            remembered = copy_uploaded_input(file_obj, "quick")
            draft = load_ui_draft()
            draft["quick_file_path"] = remembered
            save_ui_draft(draft)
            msg = f"Remembered file: `{remembered}`" if remembered else ""
            return remembered, msg

        def on_voice_browser_refresh(engine_label: str):
            catalog = voice_catalog_for_engine(engine_label)
            pager = _voice_browser_pager_updates(catalog, 0, gr)
            return (catalog, *pager)

        def on_voice_browser_prev(catalog: list[dict[str, str]], page_idx: int):
            return _voice_browser_pager_updates(catalog or [], int(page_idx) - 1, gr)

        def on_voice_browser_next(catalog: list[dict[str, str]], page_idx: int):
            return _voice_browser_pager_updates(catalog or [], int(page_idx) + 1, gr)

        def on_refresh_projects(selected_project: Optional[str] = None):
            inventory = collect_project_inventory()
            choices = list(inventory.keys())
            selected = choose_resume_project_id(inventory, selected_project)
            details = project_meta_to_markdown(inventory.get(selected))
            return gr.Dropdown(choices=choices, value=selected), inventory, details, ""

        def on_resume_last_projects():
            inventory = collect_project_inventory()
            choices = list(inventory.keys())
            selected = choose_resume_project_id(inventory, selected_project=None, prefer_last=True)
            details = project_meta_to_markdown(inventory.get(selected))
            return gr.Dropdown(choices=choices, value=selected), inventory, details, ""

        def on_project_select(project_id: Optional[str], project_map: dict[str, dict[str, str]]):
            if not project_id:
                return "_No project selected._"
            return project_meta_to_markdown((project_map or {}).get(project_id))

        def on_load_project(project_id: Optional[str], project_map: dict[str, dict[str, str]]):
            if not project_id:
                return (
                    "Select a project first.",
                    "",
                    "_No data yet._",
                    "_No chapter preview yet._",
                    [],
                    [],
                    "",
                    "",
                    "",
                    gr.Textbox(value=""),
                    runtime_state_badge("idle", "No project selected"),
                    "_No project selected._",
                )
            meta = (project_map or {}).get(project_id)
            if not meta:
                return (
                    "Project entry not found. Press Refresh.",
                    "",
                    "_No data yet._",
                    "_No chapter preview yet._",
                    [],
                    [],
                    "",
                    "",
                    "",
                    gr.Textbox(value=""),
                    runtime_state_badge("idle", "Project not found"),
                    "_No project selected._",
                )
            try:
                if meta.get("storage") == "output":
                    output_path = str(meta.get("output_path", "") or "")
                    details = project_meta_to_markdown(meta)
                    return (
                        "Output entry selected. Use 'Open Output' to play/download directly.",
                        "",
                        "_No data yet._",
                        "_No chapter preview yet._",
                        [],
                        [],
                        "",
                        "",
                        "",
                        gr.Textbox(value=""),
                        runtime_state_badge("completed", "Output ready"),
                        details,
                    )
                if meta.get("storage") == "cloud":
                    cloud_url = str(meta.get("cloud_url", "") or "")
                    manifest = load_manifest_from_free_cloud(cloud_url)
                    title = manifest.get("book", {}).get("title", "Cloud_Manifest")
                    cloud_fingerprint = hashlib.md5(cloud_url.strip().encode("utf-8")).hexdigest()[:10]
                    manifest_path = str(MANIFESTS_DIR / f"{slugify(title)}_{cloud_fingerprint}_cloud_manifest.json")
                    save_manifest(manifest, manifest_path)
                else:
                    manifest_path = str(meta.get("manifest_path", "") or "")
                    manifest = load_manifest(manifest_path)
                    manifest = ensure_manifest_defaults(manifest)
                    cloud_url = str(manifest.get("runtime", {}).get("cloud_backup", {}).get("url", "") or "")
                chapter_rows = build_chapter_table(manifest)
                preview_md = build_chapter_preview_markdown(manifest)
                char_rows = build_character_table(manifest)
                pron_rows_out = pronunciation_overrides_to_rows(manifest.get("settings", {}).get("pronunciation_overrides", {}))
                estimate = int(manifest.get("progress", {}).get("estimated_remaining_seconds", 0))
                parse_msg = (
                    f"Loaded **{manifest.get('book', {}).get('title', 'project')}** with "
                    f"**{manifest.get('progress', {}).get('total_segments', 0)}** segments."
                )
                details = project_meta_to_markdown(
                    {
                        "title": str(manifest.get("book", {}).get("title", "-")),
                        "state": str(manifest.get("runtime", {}).get("state", "-")),
                        "storage": meta.get("storage", "local"),
                        "manifest_path": manifest_path,
                        "output_path": meta.get("output_path", ""),
                        "cloud_url": cloud_url,
                    }
                )
                remember_last_project(project_id=project_id, manifest_path=manifest_path, cloud_url=cloud_url)
                return (
                    "Project loaded.",
                    parse_msg,
                    rows_to_markdown(["Chapter", "Segments", "Characters Found", "Cache Status"], chapter_rows),
                    preview_md,
                    char_rows,
                    pron_rows_out,
                    f"Estimated generation time: **~{estimate // 60} min {estimate % 60}s**",
                    manifest_path,
                    cloud_url,
                    gr.Textbox(value=cloud_url),
                    runtime_state_badge(str(manifest.get("runtime", {}).get("state", "idle")), "Project loaded"),
                    details,
                )
            except Exception as exc:
                return (
                    f"Failed to load project: {exc}",
                    "",
                    "_No data yet._",
                    "_No chapter preview yet._",
                    [],
                    [],
                    "",
                    "",
                    "",
                    gr.Textbox(value=""),
                    runtime_state_badge("failed", "Load failed"),
                    project_meta_to_markdown(meta),
                )

        def on_delete_project(project_id: Optional[str], project_map: dict[str, dict[str, str]]):
            if not project_id:
                return "Select a project first.", gr.Dropdown(), project_map, "_No project selected._"
            meta = (project_map or {}).get(project_id)
            if not meta:
                return "Project entry not found. Press Refresh.", gr.Dropdown(), project_map, "_No project selected._"
            try:
                if meta.get("storage") == "cloud":
                    return (
                        "Cloud backups are immutable on JSONBlob. Remove local manifests instead.",
                        gr.Dropdown(),
                        project_map,
                        project_meta_to_markdown(meta),
                    )
                manifest_path = Path(str(meta.get("manifest_path", "")))
                with contextlib.suppress(Exception):
                    manifest_path.unlink()
                with contextlib.suppress(Exception):
                    manifest_path.with_suffix(manifest_path.suffix + ".bak").unlink()
                app_state = load_app_state()
                if str(app_state.get("last_manifest_path", "") or "") == str(manifest_path):
                    app_state.pop("last_project_id", None)
                    app_state.pop("last_manifest_path", None)
                    app_state.pop("last_cloud_url", None)
                    save_app_state(app_state)
                inventory = collect_project_inventory()
                choices = list(inventory.keys())
                selected = choices[0] if choices else None
                details = project_meta_to_markdown(inventory.get(selected))
                return "Project deleted.", gr.Dropdown(choices=choices, value=selected), inventory, details
            except Exception as exc:
                return f"Delete failed: {exc}", gr.Dropdown(), project_map, project_meta_to_markdown(meta)

        def on_open_project_output(project_id: Optional[str], project_map: dict[str, dict[str, str]]):
            if not project_id:
                return "Select a project first.", None, None, None, None
            meta = (project_map or {}).get(project_id, {})
            output_path = str(meta.get("output_path", "") or "")
            if not output_path:
                return "No output file is linked for this project yet.", None, None, None, None
            if not Path(output_path).exists():
                return "Output file is missing from disk.", None, None, None, None
            msg = f"Opened output: `{output_path}`"
            return msg, output_path, output_path, output_path, output_path

        def on_preview(engine_label: str, voice: str):
            if not voice:
                return None
            engine = create_tts_engine(normalize_engine_label(engine_label))
            result = engine.preview(voice)
            return result.audio_path

        def on_parse(
            input_mode_label: str,
            file_obj: Any,
            remembered_adv_file: str,
            url: str,
            text: str,
            engine_label: str,
            narrator: str,
            dialogue: str,
            speed: float,
            speed_mode_label: str,
            pron_rows: Any,
            low_mem: bool,
            cache_mb: float,
            cloud_enabled: bool,
            cloud_url: str,
        ):
            try:
                input_path, parsed_url, parsed_text = resolve_source_inputs(
                    input_mode_label,
                    file_obj,
                    url,
                    text,
                    fallback_file_path=remembered_adv_file,
                )
                engine_name = normalize_engine_label(engine_label)
                norm_speed_mode = normalize_speed_mode_label(speed_mode_label)
                narrator = narrator or "en-US-GuyNeural"
                dialogue = dialogue or "en-US-JennyNeural"
                max_concurrent = 1 if low_mem else create_tts_engine(engine_name).max_concurrent
                settings = {
                    "tts_engine": engine_name,
                    "narrator_voice": narrator,
                    "dialogue_voice": dialogue,
                    "character_voices": {},
                    "pronunciation_overrides": parse_pronunciation_table(pron_rows),
                    "speed_multiplier": float(speed),
                    "speed_mode": norm_speed_mode,
                    "max_concurrent": max_concurrent,
                    "max_queue_size": 8 if low_mem else 32,
                    "cache_max_size_mb": int(cache_mb),
                    "background_music": None,
                    "music_duck_db": -15,
                    "output_format": "m4b",
                    "enable_free_cloud_memory": bool(cloud_enabled),
                    "free_cloud_manifest_url": str(cloud_url or ""),
                }
                manifest, manifest_path = stage_parse(
                    input_path=input_path,
                    settings=settings,
                    url=parsed_url,
                    raw_text=parsed_text,
                )
                cloud_url_effective = str(cloud_url or "")
                cloud_warning = ""
                if cloud_enabled and not cloud_url_effective:
                    try:
                        cloud_url_effective = upload_manifest_to_free_cloud(manifest)
                        manifest.setdefault("runtime", {}).setdefault("cloud_backup", {})
                        manifest["runtime"]["cloud_backup"]["enabled"] = True
                        manifest["runtime"]["cloud_backup"]["url"] = cloud_url_effective
                        manifest["settings"]["free_cloud_manifest_url"] = cloud_url_effective
                        save_manifest(manifest, manifest_path)
                    except Exception as exc:
                        cloud_warning = f" Cloud backup warning: {exc}"
                chapter_rows = build_chapter_table(manifest)
                preview_md = build_chapter_preview_markdown(manifest)
                char_rows = build_character_table(manifest)
                pron_rows_out = pronunciation_overrides_to_rows(manifest.get("settings", {}).get("pronunciation_overrides", {}))
                estimate = int(manifest["progress"].get("estimated_remaining_seconds", 0))
                remember_last_project(
                    project_id=f"local::{manifest_path}",
                    manifest_path=manifest_path,
                    cloud_url=cloud_url_effective,
                )
                status = (
                    f"Parsed **{len(manifest.get('chapters', []))}** chapters, "
                    f"**{manifest['progress']['total_segments']}** segments. "
                    f"Estimated generation: **~{estimate // 60} min**."
                )
                if cloud_warning:
                    status += cloud_warning
                return (
                    status,
                    rows_to_markdown(["Chapter", "Segments", "Characters Found", "Cache Status"], chapter_rows),
                    preview_md,
                    char_rows,
                    pron_rows_out,
                    f"Estimated generation time: **~{estimate // 60} min {estimate % 60}s**",
                    manifest_path,
                    cloud_url_effective,
                    gr.Textbox(value=cloud_url_effective),
                )
            except Exception as exc:
                return (f"Parse failed: {exc}", "_No data yet._", "_No chapter preview yet._", [], [], "", "", "", gr.Textbox(value=""))

        def on_cancel(manifest_path: str):
            cancel_event.set()
            if manifest_path:
                with contextlib.suppress(Exception):
                    manifest = load_manifest(manifest_path)
                    update_run_state(manifest, "cancel_requested", "User requested cancellation", manifest_path)
            return (
                "Cancellation requested. Current segment(s) will finish then stop.",
                runtime_state_badge("cancel_requested", "Stopping safely..."),
            )

        def on_quick_cancel():
            cancel_event.set()
            return "Cancellation requested.", runtime_state_badge("cancel_requested", "Stopping...")

        def on_generate(
            manifest_path: str,
            engine_label: str,
            narrator: str,
            dialogue: str,
            speed: float,
            speed_mode_label: str,
            char_rows: Any,
            pron_rows: Any,
            out_fmt: str,
            do_normalize: bool,
            music_obj: Any,
            music_db: float,
            low_mem: bool,
            cache_mb: float,
            cloud_enabled: bool,
            cloud_url: str,
            progress=gr.Progress(),
        ):
            if not manifest_path:
                return (
                    "Parse a book first.",
                    "_No data yet._",
                    None,
                    None,
                    runtime_state_badge("idle", "No manifest loaded"),
                )
            cancel_event.clear()
            try:
                manifest = load_manifest(manifest_path)
                manifest = ensure_manifest_defaults(manifest)
                settings = manifest.get("settings", {})
                settings["tts_engine"] = normalize_engine_label(engine_label)
                settings["narrator_voice"] = narrator or settings.get("narrator_voice", "en-US-GuyNeural")
                settings["dialogue_voice"] = dialogue or settings.get("dialogue_voice", "en-US-JennyNeural")
                settings["speed_multiplier"] = float(speed)
                settings["speed_mode"] = normalize_speed_mode_label(speed_mode_label)
                parsed_pron = parse_pronunciation_table(pron_rows)
                if parsed_pron:
                    settings["pronunciation_overrides"] = parsed_pron
                else:
                    settings["pronunciation_overrides"] = settings.get("pronunciation_overrides", {})
                settings["music_duck_db"] = float(music_db)
                settings["background_music"] = getattr(music_obj, "name", None) if music_obj else None
                settings["output_format"] = "m4b" if out_fmt.lower().startswith("m4b") else "mp3"
                settings["max_concurrent"] = 1 if low_mem else int(create_tts_engine(settings["tts_engine"]).max_concurrent)
                settings["max_queue_size"] = 8 if low_mem else 32
                settings["cache_max_size_mb"] = int(cache_mb)
                settings["enable_free_cloud_memory"] = bool(cloud_enabled)
                settings["free_cloud_manifest_url"] = str(cloud_url or "")

                updated_char_map: dict[str, dict[str, Any]] = {}
                for row in (char_rows or []):
                    if not row or len(row) < 2:
                        continue
                    character = str(row[0]).strip()
                    voice = str(row[1]).strip()
                    detected_by = str(row[2]).strip() if len(row) > 2 else "manual"
                    if character and voice:
                        updated_char_map[character] = {"voice": voice, "detected_by": detected_by or "manual"}
                if updated_char_map:
                    settings["character_voices"] = updated_char_map
                apply_character_voices_to_segments(manifest, settings.get("character_voices", {}))

                manifest["settings"] = settings
                segments_need_generation = any(
                    seg.get("status") != "cached"
                    for chap in manifest.get("chapters", [])
                    for seg in chap.get("segments", [])
                )
                if segments_need_generation:
                    manifest.setdefault("runtime", {})["assembly"] = {
                        "concat_done": False,
                        "music_mixed": False,
                        "speed_adjusted": False,
                        "normalized": False,
                        "output_done": False,
                    }
                update_run_state(manifest, "idle", "Ready to generate", manifest_path=None)
                book_key = make_book_profile_key(manifest.get("book", {}))
                save_book_profile(
                    book_key,
                    settings.get("character_voices", {}),
                    settings.get("pronunciation_overrides", {}),
                )
                save_manifest(manifest, manifest_path)

                run_started = time.time()

                def progress_cb(done: int, total: int, desc: str) -> None:
                    ratio = done / total if total else 1.0
                    elapsed = max(0.001, time.time() - run_started)
                    rate = done / elapsed if done > 0 else 0.0
                    remaining = max(0, total - done)
                    eta = (remaining / rate) if rate > 0 else 0.0
                    rich_desc = (
                        f"Segment {done}/{total} · ETA {format_eta(eta)}"
                        + (f" · {desc}" if desc else "")
                    )
                    progress(ratio, desc=rich_desc)

                progress(0, desc="Generating segment audio")
                manifest = run_coro_sync(
                    stage_generate(
                        manifest=manifest,
                        manifest_path=manifest_path,
                        cancel_event=cancel_event,
                        progress_callback=progress_cb,
                    )
                )

                if cancel_event.is_set():
                    progress_rows = build_chapter_progress(manifest)
                    return (
                        "Generation cancelled.",
                        rows_to_markdown(["Chapter", "Status", "Segments Done"], progress_rows),
                        None,
                        None,
                        runtime_state_badge("cancelled", "Generation cancelled"),
                    )

                progress(0.92, desc="Assembling final audiobook")
                output_path = stage_assemble(
                    manifest=manifest,
                    output_format=settings["output_format"],
                    normalize_audio=bool(do_normalize),
                    manifest_path=manifest_path,
                    cancel_event=cancel_event,
                )
                progress(1.0, desc="Done")
                if settings.get("enable_free_cloud_memory"):
                    try:
                        cloud_link = upload_manifest_to_free_cloud(manifest)
                        settings["free_cloud_manifest_url"] = cloud_link
                        manifest["runtime"]["cloud_backup"] = {"enabled": True, "url": cloud_link}
                        cloud_backup_note = f" Cloud backup updated: {cloud_link}"
                    except Exception as exc:
                        cloud_backup_note = f" Cloud backup warning: {exc}"
                else:
                    cloud_backup_note = ""
                remember_last_project(
                    project_id=f"local::{manifest_path}",
                    manifest_path=manifest_path,
                    cloud_url=str(settings.get("free_cloud_manifest_url", "") or ""),
                )
                save_manifest(manifest, manifest_path)
                progress_rows = build_chapter_progress(manifest)
                return (
                    f"Generation complete.{cloud_backup_note}",
                    rows_to_markdown(["Chapter", "Status", "Segments Done"], progress_rows),
                    output_path,
                    output_path,
                    runtime_state_badge("completed", "Output ready" if not cloud_backup_note else "Output ready (check note)"),
                )
            except Exception as exc:
                if "manifest" in locals():
                    update_run_state(manifest, "failed", f"Generation failed: {exc}", manifest_path)
                return (
                    f"Generation failed: {exc}",
                    "_No data yet._",
                    None,
                    None,
                    runtime_state_badge("failed", "Check logs and retry"),
                )

        def on_refresh_preflight():
            return run_preflight_checks()

        def on_cloud_backup(manifest_path: str):
            if not manifest_path:
                return "No manifest loaded. Parse a book first.", "", gr.Textbox(value="")
            try:
                manifest = load_manifest(manifest_path)
                cloud_link = upload_manifest_to_free_cloud(manifest)
                manifest.setdefault("runtime", {}).setdefault("cloud_backup", {})
                manifest["runtime"]["cloud_backup"]["enabled"] = True
                manifest["runtime"]["cloud_backup"]["url"] = cloud_link
                manifest.setdefault("settings", {})["enable_free_cloud_memory"] = True
                manifest["settings"]["free_cloud_manifest_url"] = cloud_link
                remember_last_project(
                    project_id=f"local::{manifest_path}",
                    manifest_path=manifest_path,
                    cloud_url=cloud_link,
                )
                save_manifest(manifest, manifest_path)
                return f"Backed up manifest to free cloud: `{cloud_link}`", cloud_link, gr.Textbox(value=cloud_link)
            except Exception as exc:
                return f"Cloud backup failed: {exc}", "", gr.Textbox(value="")

        def on_cloud_restore(cloud_url: str):
            if not cloud_url or not cloud_url.strip():
                return (
                    "Enter a cloud manifest URL first.",
                    "",
                    "_No data yet._",
                    "_No chapter preview yet._",
                    [],
                    [],
                    "",
                    "",
                    "",
                    gr.Textbox(value=""),
                )
            try:
                manifest = load_manifest_from_free_cloud(cloud_url)
                manifest = ensure_manifest_defaults(manifest)
                title = manifest.get("book", {}).get("title", "Cloud_Manifest")
                cloud_fingerprint = hashlib.md5(cloud_url.strip().encode("utf-8")).hexdigest()[:10]
                manifest_name = f"{slugify(title)}_{cloud_fingerprint}_cloud_manifest.json"
                manifest_path = str(MANIFESTS_DIR / manifest_name)
                manifest.setdefault("runtime", {}).setdefault("cloud_backup", {})
                manifest["runtime"]["cloud_backup"]["enabled"] = True
                manifest["runtime"]["cloud_backup"]["url"] = cloud_url.strip()
                manifest.setdefault("settings", {})["enable_free_cloud_memory"] = True
                manifest["settings"]["free_cloud_manifest_url"] = cloud_url.strip()
                save_manifest(manifest, manifest_path)
                chapter_rows = build_chapter_table(manifest)
                preview_md = build_chapter_preview_markdown(manifest)
                char_rows = build_character_table(manifest)
                pron_rows_out = pronunciation_overrides_to_rows(manifest.get("settings", {}).get("pronunciation_overrides", {}))
                estimate = int(manifest.get("progress", {}).get("estimated_remaining_seconds", 0))
                parse_msg = (
                    f"Loaded cloud manifest with **{len(manifest.get('chapters', []))}** chapters and "
                    f"**{manifest.get('progress', {}).get('total_segments', 0)}** segments."
                )
                remember_last_project(
                    project_id=f"local::{manifest_path}",
                    manifest_path=manifest_path,
                    cloud_url=cloud_url.strip(),
                )
                return (
                    "Cloud manifest restored.",
                    parse_msg,
                    rows_to_markdown(["Chapter", "Segments", "Characters Found", "Cache Status"], chapter_rows),
                    preview_md,
                    char_rows,
                    pron_rows_out,
                    f"Estimated generation time: **~{estimate // 60} min {estimate % 60}s**",
                    manifest_path,
                    cloud_url.strip(),
                    gr.Textbox(value=cloud_url.strip()),
                )
            except Exception as exc:
                return (
                    f"Cloud restore failed: {exc}",
                    "",
                    "_No data yet._",
                    "_No chapter preview yet._",
                    [],
                    [],
                    "",
                    "",
                    "",
                    gr.Textbox(value=""),
                )

        def on_input_mode_change(mode_label: str):
            mode = (mode_label or "File").lower()
            return (
                gr.File(visible="file" in mode),
                gr.Textbox(visible="url" in mode),
                gr.Textbox(visible=("paste" in mode or "text" in mode)),
            )

        def on_quick_generate(
            input_mode_label: str,
            file_obj: Any,
            remembered_quick_file: str,
            url: str,
            text: str,
            output_fmt: str,
            use_cloud_memory: bool,
            progress=gr.Progress(),
        ):
            cancel_event.clear()
            input_path, parsed_url, parsed_text = resolve_source_inputs(
                input_mode_label,
                file_obj,
                url,
                text,
                fallback_file_path=remembered_quick_file,
            )
            if not input_path and not parsed_url and not parsed_text:
                return (
                    "Please provide a file, URL, or text.",
                    runtime_state_badge("idle", "Waiting for input"),
                    "_No chapter preview yet._",
                    None,
                    None,
                    "",
                )
            primary_engine = "edge-tts"
            narrator = "en-US-GuyNeural"
            dialogue = "en-US-JennyNeural"
            output_mode = "m4b" if str(output_fmt).lower().startswith("m4b") else "mp3"
            settings = {
                "tts_engine": primary_engine,
                "narrator_voice": narrator,
                "dialogue_voice": dialogue,
                "character_voices": {},
                "pronunciation_overrides": {},
                "speed_multiplier": 1.0,
                "speed_mode": "post_process",
                "max_concurrent": 1,
                "max_queue_size": 8,
                "cache_max_size_mb": 512,
                "background_music": None,
                "music_duck_db": -15,
                "output_format": output_mode,
                "enable_free_cloud_memory": bool(use_cloud_memory),
                "free_cloud_manifest_url": "",
            }
            try:
                progress(0.01, desc="📖 Parsing text into chapters...")
                manifest, manifest_path = stage_parse(
                    input_path=input_path,
                    settings=settings,
                    url=parsed_url,
                    raw_text=parsed_text,
                )
                preview_md = build_chapter_preview_markdown(manifest)
                remember_last_project(project_id=f"local::{manifest_path}", manifest_path=manifest_path, cloud_url="")

                def progress_cb(done: int, total: int, desc: str) -> None:
                    ratio = 0.05 + ((done / total) * 0.8 if total else 0.8)
                    emoji = "🎵" if total > 0 else "⏳"
                    progress(min(ratio, 0.9), desc=f"{emoji} {done}/{total}: {desc}")

                progress(0.05, desc="🎙️ Generating audio from text...")
                manifest = run_coro_sync(
                    stage_generate(
                        manifest=manifest,
                        manifest_path=manifest_path,
                        cancel_event=cancel_event,
                        progress_callback=progress_cb,
                    )
                )
                if cancel_event.is_set():
                    return (
                        "Generation cancelled.",
                        runtime_state_badge("cancelled", "Stopped by user"),
                        preview_md,
                        None,
                        None,
                        "",
                    )
                if manifest_has_generation_errors(manifest):
                    progress(0.55, desc="⚠️ Retrying with offline engine")
                    fallback_settings = manifest.get("settings", {})
                    fallback_settings["tts_engine"] = "kokoro"
                    fallback_settings["narrator_voice"] = "af_sarah"
                    fallback_settings["dialogue_voice"] = "bf_emma"
                    manifest["settings"] = fallback_settings
                    for chapter in manifest.get("chapters", []):
                        for segment in chapter.get("segments", []):
                            if segment.get("status") == "cached":
                                continue
                            segment["status"] = "pending"
                            segment["cache_file"] = None
                            segment["duration_seconds"] = None
                            segment.pop("error", None)
                            if segment.get("speaker") in (None, "", "narrator"):
                                segment["voice"] = "af_sarah"
                            else:
                                segment["voice"] = "bf_emma"
                    save_manifest(manifest, manifest_path)
                    manifest = run_coro_sync(
                        stage_generate(
                            manifest=manifest,
                            manifest_path=manifest_path,
                            cancel_event=cancel_event,
                            progress_callback=progress_cb,
                        )
                    )
                    if manifest_has_generation_errors(manifest):
                        raise RuntimeError("Generation failed with both edge-tts and kokoro fallback.")

                progress(0.92, desc="📦 Assembling final audiobook")
                output_path = stage_assemble(
                    manifest=manifest,
                    output_format=output_mode,
                    normalize_audio=True,
                    manifest_path=manifest_path,
                    cancel_event=cancel_event,
                )

                cloud_url = ""
                cloud_backup_warning = ""
                if use_cloud_memory:
                    try:
                        cloud_url = upload_manifest_to_free_cloud(manifest)
                        manifest["runtime"]["cloud_backup"] = {"enabled": True, "url": cloud_url}
                        manifest["settings"]["free_cloud_manifest_url"] = cloud_url
                        save_manifest(manifest, manifest_path)
                    except Exception as exc:
                        cloud_backup_warning = f" Cloud backup warning: {exc}"
                remember_last_project(
                    project_id=f"local::{manifest_path}",
                    manifest_path=manifest_path,
                    cloud_url=cloud_url,
                )
                progress(1.0, desc="✅ Complete! Ready to download")
                cloud_line = f"\n☁️ Cloud URL: `{cloud_url}`" if cloud_url else ""
                status = f"✅ Done! Your audiobook is ready to play or download.{cloud_line}"
                if cloud_backup_warning:
                    status += f"\n{cloud_backup_warning}"
                return (
                    status,
                    runtime_state_badge("completed", "Quick flow complete" if not cloud_backup_warning else "Quick flow complete (backup warning)"),
                    preview_md,
                    output_path,
                    output_path,
                    cloud_url,
                )
            except Exception as exc:
                return (
                    f"Quick mode failed: {exc}",
                    runtime_state_badge("failed", "Quick flow failed"),
                    "_No chapter preview yet._",
                    None,
                    None,
                    "",
                )

        voice_browser_outputs = [voice_page_state, voice_page_label, voice_prev_page_btn, voice_next_page_btn]
        for label_component, value_component, button_component in zip(
            voice_browser_labels, voice_browser_values, voice_browser_buttons
        ):
            voice_browser_outputs.extend([label_component, value_component, button_component])

        engine_change_evt = engine_select.change(
            on_engine_change,
            inputs=[engine_select],
            outputs=[narrator_voice, dialogue_voice],
        )
        engine_change_evt.then(
            on_voice_browser_refresh,
            inputs=[engine_select],
            outputs=[voice_catalog_state, *voice_browser_outputs],
        )
        app.load(
            on_refresh_projects,
            inputs=[project_selector],
            outputs=[project_selector, project_map_state, project_details, project_action_status],
        )
        restore_draft_evt = app.load(
            on_restore_ui_draft,
            inputs=[],
            outputs=[
                input_mode,
                url_input,
                text_input,
                quick_input_mode,
                quick_url_input,
                quick_text_input,
                quick_output_format,
                quick_free_cloud,
                cloud_manifest_url,
                remembered_adv_file_state,
                remembered_quick_file_state,
                draft_restore_info_md,
                quick_draft_restore_md,
            ],
        )
        restore_draft_evt.then(on_input_mode_change, inputs=[input_mode], outputs=[file_input, url_input, text_input])
        restore_draft_evt.then(
            on_input_mode_change,
            inputs=[quick_input_mode],
            outputs=[quick_file_input, quick_url_input, quick_text_input],
        )
        app.load(
            on_voice_browser_refresh,
            inputs=[engine_select],
            outputs=[voice_catalog_state, *voice_browser_outputs],
        )
        refresh_projects_btn.click(
            on_refresh_projects,
            inputs=[project_selector],
            outputs=[project_selector, project_map_state, project_details, project_action_status],
        )
        resume_evt = resume_last_btn.click(
            on_resume_last_projects,
            inputs=[],
            outputs=[project_selector, project_map_state, project_details, project_action_status],
        )
        resume_evt.then(
            on_load_project,
            inputs=[project_selector, project_map_state],
            outputs=[
                project_action_status,
                parse_status,
                chapter_list_md,
                chapter_preview_md,
                character_table,
                pronunciation_table,
                time_estimate,
                manifest_path_state,
                cloud_url_state,
                cloud_manifest_url,
                generation_badge,
                project_details,
            ],
        )
        project_selector.change(on_project_select, inputs=[project_selector, project_map_state], outputs=[project_details])
        load_project_btn.click(
            on_load_project,
            inputs=[project_selector, project_map_state],
            outputs=[
                project_action_status,
                parse_status,
                chapter_list_md,
                chapter_preview_md,
                character_table,
                pronunciation_table,
                time_estimate,
                manifest_path_state,
                cloud_url_state,
                cloud_manifest_url,
                generation_badge,
                project_details,
            ],
        )
        delete_project_btn.click(
            on_delete_project,
            inputs=[project_selector, project_map_state],
            outputs=[project_action_status, project_selector, project_map_state, project_details],
        )
        open_output_btn.click(
            on_open_project_output,
            inputs=[project_selector, project_map_state],
            outputs=[project_action_status, audio_player, download_file, quick_player, quick_download],
        )
        file_input.change(on_adv_file_upload, inputs=[file_input], outputs=[remembered_adv_file_state, draft_restore_info_md])
        quick_file_input.change(
            on_quick_file_upload,
            inputs=[quick_file_input],
            outputs=[remembered_quick_file_state, quick_draft_restore_md],
        )
        input_mode.change(on_input_mode_change, inputs=[input_mode], outputs=[file_input, url_input, text_input])
        quick_input_mode.change(
            on_input_mode_change,
            inputs=[quick_input_mode],
            outputs=[quick_file_input, quick_url_input, quick_text_input],
        )
        narrator_preview.click(
            on_preview,
            inputs=[engine_select, narrator_voice],
            outputs=[narrator_audio],
        )
        dialogue_preview.click(
            on_preview,
            inputs=[engine_select, dialogue_voice],
            outputs=[dialogue_audio],
        )
        parse_evt = parse_btn.click(
            on_parse,
            inputs=[
                input_mode,
                file_input,
                remembered_adv_file_state,
                url_input,
                text_input,
                engine_select,
                narrator_voice,
                dialogue_voice,
                speed_slider,
                speed_mode,
                pronunciation_table,
                low_memory_mode,
                cache_size_mb,
                free_cloud_memory,
                cloud_manifest_url,
            ],
            outputs=[
                parse_status,
                chapter_list_md,
                chapter_preview_md,
                character_table,
                pronunciation_table,
                time_estimate,
                manifest_path_state,
                cloud_url_state,
                cloud_manifest_url,
            ],
        )
        parse_evt.then(
            on_refresh_projects,
            inputs=[project_selector],
            outputs=[project_selector, project_map_state, project_details, project_action_status],
        )
        cancel_btn.click(on_cancel, inputs=[manifest_path_state], outputs=[progress_text, generation_badge])
        generate_btn.click(
            on_generate,
            inputs=[
                manifest_path_state,
                engine_select,
                narrator_voice,
                dialogue_voice,
                speed_slider,
                speed_mode,
                character_table,
                pronunciation_table,
                output_format,
                normalize_check,
                music_file,
                music_volume,
                low_memory_mode,
                cache_size_mb,
                free_cloud_memory,
                cloud_manifest_url,
            ],
            outputs=[progress_text, chapter_progress_md, audio_player, download_file, generation_badge],
        )
        quick_evt = quick_generate_btn.click(
            on_quick_generate,
            inputs=[
                quick_input_mode,
                quick_file_input,
                remembered_quick_file_state,
                quick_url_input,
                quick_text_input,
                quick_output_format,
                quick_free_cloud,
            ],
            outputs=[quick_status, quick_state_badge, quick_chapter_preview_md, quick_player, quick_download, quick_cloud_url],
        )
        for component in [
            input_mode,
            url_input,
            text_input,
            quick_input_mode,
            quick_url_input,
            quick_text_input,
            quick_output_format,
            quick_free_cloud,
            cloud_manifest_url,
        ]:
            component.change(
                on_save_ui_draft,
                inputs=[
                    input_mode,
                    url_input,
                    text_input,
                    quick_input_mode,
                    quick_url_input,
                    quick_text_input,
                    quick_output_format,
                    quick_free_cloud,
                    cloud_manifest_url,
                    remembered_adv_file_state,
                    remembered_quick_file_state,
                ],
                outputs=[draft_saved_state],
            )
        quick_evt.then(
            on_refresh_projects,
            inputs=[project_selector],
            outputs=[project_selector, project_map_state, project_details, project_action_status],
        )
        quick_cancel_btn.click(on_quick_cancel, outputs=[quick_status, quick_state_badge])
        refresh_preflight_btn.click(on_refresh_preflight, outputs=[preflight_table])
        backup_cloud_btn.click(on_cloud_backup, inputs=[manifest_path_state], outputs=[cloud_status, cloud_url_state, cloud_manifest_url])
        restore_evt = restore_cloud_btn.click(
            on_cloud_restore,
            inputs=[cloud_manifest_url],
            outputs=[
                cloud_status,
                parse_status,
                chapter_list_md,
                chapter_preview_md,
                character_table,
                pronunciation_table,
                time_estimate,
                manifest_path_state,
                cloud_url_state,
                cloud_manifest_url,
            ],
        )
        restore_evt.then(
            on_refresh_projects,
            inputs=[project_selector],
            outputs=[project_selector, project_map_state, project_details, project_action_status],
        )
        voice_prev_page_btn.click(
            on_voice_browser_prev,
            inputs=[voice_catalog_state, voice_page_state],
            outputs=voice_browser_outputs,
        )
        voice_next_page_btn.click(
            on_voice_browser_next,
            inputs=[voice_catalog_state, voice_page_state],
            outputs=voice_browser_outputs,
        )
        for button, voice_value in zip(voice_browser_buttons, voice_browser_values):
            button.click(
                on_preview,
                inputs=[engine_select, voice_value],
                outputs=[voice_browser_audio],
            )

    return app


def main() -> None:
    ensure_runtime_dirs()
    app = build_ui()
    share_flag = str(os.environ.get("GRADIO_SHARE", "0")).lower() in {"1", "true", "yes"}
    app.launch(server_name="0.0.0.0", server_port=7860, show_api=False, share=share_flag)


if __name__ == "__main__":
    main()
