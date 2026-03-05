"""
src_manifest.py — Audiobook Creator V7
Manifest schema, ManifestManager, AudioCache (LRU), pipeline stage stubs,
RetryPolicy, GenerationSession, and EstimationEngine.
"""

from __future__ import annotations

import hashlib
import json
import os
import random
import shutil
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Generator, Iterator, Optional

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MANIFEST_VERSION = "7.0"
MANIFEST_FILENAME = "manifest.json"
MANIFESTS_DIR = "manifests"
DEFAULT_CACHE_DIR = "tts_cache"
DEFAULT_MAX_CACHE_MB = 500

# Segment / chapter status literals
STATUS_PENDING = "pending"
STATUS_IN_PROGRESS = "in_progress"
STATUS_COMPLETE = "complete"
STATUS_CACHED = "cached"
STATUS_ERROR = "error"

# Segment type literals
SEGMENT_NARRATION = "narration"
SEGMENT_DIALOGUE = "dialogue"
SEGMENT_SFX = "sfx"
SEGMENT_SCENE_BREAK = "scene_break"


# ---------------------------------------------------------------------------
# RetryPolicy
# ---------------------------------------------------------------------------

@dataclass
class RetryPolicy:
    """Retry configuration used when TTS calls fail.

    Attributes:
        max_retries: Maximum number of retry attempts after the initial failure.
        backoff_seconds: Base wait time between retries (exponential backoff is
            applied: attempt * backoff_seconds).
        jitter: When True, adds a random ±20 % jitter to the backoff delay to
            avoid thundering-herd problems against the TTS service.
    """

    max_retries: int = 3
    backoff_seconds: float = 2.0
    jitter: bool = True

    def wait_time(self, attempt: int) -> float:
        """Return the number of seconds to sleep before *attempt* (1-indexed).

        Args:
            attempt: The retry attempt number, starting at 1.

        Returns:
            Sleep duration in seconds.
        """
        delay = self.backoff_seconds * attempt
        if self.jitter:
            delay *= 1.0 + random.uniform(-0.2, 0.2)
        return max(0.0, delay)

    def execute(self, fn, *args, **kwargs):
        """Call *fn* with retry semantics defined by this policy.

        Args:
            fn: Callable to execute.
            *args: Positional arguments forwarded to *fn*.
            **kwargs: Keyword arguments forwarded to *fn*.

        Returns:
            The return value of *fn* on success.

        Raises:
            The last exception raised by *fn* once all retries are exhausted.
        """
        last_exc: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                return fn(*args, **kwargs)
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                if attempt < self.max_retries:
                    time.sleep(self.wait_time(attempt + 1))
        raise last_exc  # type: ignore[misc]


# ---------------------------------------------------------------------------
# ManifestManager
# ---------------------------------------------------------------------------

def _default_settings() -> dict[str, Any]:
    """Return the canonical default settings block."""
    return {
        "tts_engine": "edge-tts",
        "narrator_voice": "en-US-GuyNeural",
        "dialogue_voice": "en-US-JennyNeural",
        "character_voices": {},
        "pronunciation_overrides": {},
        "speed_multiplier": 1.0,
        "background_music": None,
        "music_duck_db": -15,
        "output_format": "m4b",
    }


def _default_progress() -> dict[str, Any]:
    """Return the canonical default progress block."""
    return {
        "total_segments": 0,
        "completed_segments": 0,
        "last_completed_chapter": -1,
        "last_completed_segment": -1,
        "generation_started": None,
        "estimated_remaining_seconds": None,
    }


class ManifestManager:
    """Create, persist, and query audiobook manifests.

    A manifest is a plain ``dict`` that can be serialised to/from JSON.
    All mutating methods return the manifest so callers can chain them.
    """

    # ------------------------------------------------------------------
    # Factory helpers
    # ------------------------------------------------------------------

    @staticmethod
    def create(input_path: str, settings: dict[str, Any] | None = None) -> dict[str, Any]:
        """Create a fresh manifest for *input_path*.

        Args:
            input_path: Absolute or relative path (or URL) of the source book.
            settings: Optional partial settings dict; missing keys are filled
                with defaults.

        Returns:
            A new manifest dict with version, book, settings, chapters, and
            progress sections populated with sensible defaults.
        """
        merged_settings = _default_settings()
        if settings:
            merged_settings.update(settings)

        source_type = ManifestManager._infer_source_type(input_path)

        manifest: dict[str, Any] = {
            "version": MANIFEST_VERSION,
            "book": {
                "title": Path(input_path).stem if not input_path.startswith("http") else input_path,
                "author": "",
                "source_file": input_path,
                "source_type": source_type,
            },
            "settings": merged_settings,
            "chapters": [],
            "progress": _default_progress(),
        }
        return manifest

    @staticmethod
    def _infer_source_type(input_path: str) -> str:
        """Return source type string from the file extension or URL prefix."""
        lower = input_path.lower()
        if lower.startswith("http://") or lower.startswith("https://"):
            return "url"
        ext = Path(lower).suffix.lstrip(".")
        if ext in {"epub", "pdf", "txt"}:
            return ext
        return "text"

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    @staticmethod
    def save(manifest: dict[str, Any], path: str | Path) -> Path:
        """Write *manifest* to *path* as indented JSON.

        Args:
            manifest: The manifest dict to serialise.
            path: Destination file path (created with parents if needed).

        Returns:
            The resolved :class:`~pathlib.Path` that was written.
        """
        dest = Path(path)
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_suffix(".tmp")
        try:
            tmp.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
            tmp.replace(dest)
        except Exception:
            tmp.unlink(missing_ok=True)
            raise
        return dest.resolve()

    @staticmethod
    def load(path: str | Path) -> dict[str, Any]:
        """Load and return a manifest from *path*.

        Args:
            path: Path to the ``manifest.json`` file.

        Returns:
            The deserialised manifest dict.

        Raises:
            FileNotFoundError: If *path* does not exist.
            ValueError: If the file is not valid JSON or has a wrong version.
        """
        dest = Path(path)
        if not dest.exists():
            raise FileNotFoundError(f"Manifest not found: {dest}")
        try:
            data = json.loads(dest.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"Manifest at {dest} is not valid JSON: {exc}") from exc

        if data.get("version") != MANIFEST_VERSION:
            raise ValueError(
                f"Manifest version mismatch: expected {MANIFEST_VERSION!r}, "
                f"got {data.get('version')!r}"
            )
        return data

    # ------------------------------------------------------------------
    # Mutation helpers
    # ------------------------------------------------------------------

    @staticmethod
    def update_segment(
        manifest: dict[str, Any],
        chapter_idx: int,
        seg_idx: int,
        cache_file: str | None,
        duration: float | None,
        status: str,
    ) -> dict[str, Any]:
        """Update a single segment's cache metadata and status.

        Also refreshes the parent chapter's status and the top-level
        ``progress`` counters.

        Args:
            manifest: The manifest dict to update (mutated in place).
            chapter_idx: Zero-based chapter index.
            seg_idx: Zero-based segment index within the chapter.
            cache_file: Path to the cached audio file, or ``None``.
            duration: Segment duration in seconds, or ``None``.
            status: One of ``"pending"``, ``"cached"``, or ``"error"``.

        Returns:
            The same manifest dict (mutated).

        Raises:
            IndexError: If *chapter_idx* or *seg_idx* are out of range.
        """
        seg = manifest["chapters"][chapter_idx]["segments"][seg_idx]
        seg["cache_file"] = cache_file
        seg["duration_seconds"] = duration
        seg["status"] = status

        ManifestManager._refresh_chapter_status(manifest, chapter_idx)
        ManifestManager._refresh_progress(manifest)
        return manifest

    @staticmethod
    def _refresh_chapter_status(manifest: dict[str, Any], chapter_idx: int) -> None:
        chapter = manifest["chapters"][chapter_idx]
        segs = chapter["segments"]
        if not segs:
            chapter["status"] = STATUS_PENDING
            return
        statuses = {s["status"] for s in segs}
        if statuses == {STATUS_CACHED}:
            chapter["status"] = STATUS_COMPLETE
        elif STATUS_CACHED in statuses or STATUS_IN_PROGRESS in statuses:
            chapter["status"] = STATUS_IN_PROGRESS
        else:
            chapter["status"] = STATUS_PENDING

    @staticmethod
    def _refresh_progress(manifest: dict[str, Any]) -> None:
        total = 0
        completed = 0
        last_chap = -1
        last_seg = -1
        for ci, chapter in enumerate(manifest["chapters"]):
            for si, seg in enumerate(chapter["segments"]):
                total += 1
                if seg["status"] == STATUS_CACHED:
                    completed += 1
                    last_chap = ci
                    last_seg = si
        prog = manifest["progress"]
        prog["total_segments"] = total
        prog["completed_segments"] = completed
        prog["last_completed_chapter"] = last_chap
        prog["last_completed_segment"] = last_seg

    # ------------------------------------------------------------------
    # Query helpers
    # ------------------------------------------------------------------

    @staticmethod
    def get_stats(manifest: dict[str, Any]) -> dict[str, Any]:
        """Return a human-friendly progress statistics dict.

        Returns:
            Dict with keys: ``total_segments``, ``completed_segments``,
            ``pending_segments``, ``error_segments``, ``pct_complete``,
            ``total_chapters``, ``completed_chapters``,
            ``estimated_remaining_seconds``.
        """
        prog = manifest["progress"]
        total = prog["total_segments"]
        completed = prog["completed_segments"]
        pending = 0
        errors = 0
        completed_chapters = 0
        for chapter in manifest["chapters"]:
            if chapter["status"] == STATUS_COMPLETE:
                completed_chapters += 1
            for seg in chapter["segments"]:
                if seg["status"] == STATUS_PENDING:
                    pending += 1
                elif seg["status"] == STATUS_ERROR:
                    errors += 1

        return {
            "total_segments": total,
            "completed_segments": completed,
            "pending_segments": pending,
            "error_segments": errors,
            "pct_complete": round(100.0 * completed / total, 2) if total else 0.0,
            "total_chapters": len(manifest["chapters"]),
            "completed_chapters": completed_chapters,
            "estimated_remaining_seconds": prog.get("estimated_remaining_seconds"),
        }

    @staticmethod
    def find_incomplete(manifest: dict[str, Any]) -> list[tuple[int, int]]:
        """Return (chapter_idx, seg_idx) pairs for all non-cached segments.

        Segments with status ``"pending"`` or ``"error"`` are considered
        incomplete and will be returned in chapter/segment order.

        Returns:
            Ordered list of ``(chapter_idx, seg_idx)`` tuples.
        """
        result: list[tuple[int, int]] = []
        for ci, chapter in enumerate(manifest["chapters"]):
            for si, seg in enumerate(chapter["segments"]):
                if seg["status"] != STATUS_CACHED:
                    result.append((ci, si))
        return result

    @staticmethod
    def find_manifest_for_book(title: str, manifests_dir: str = MANIFESTS_DIR) -> Path | None:
        """Search *manifests_dir* for an existing manifest whose book title matches.

        The comparison is case-insensitive and normalises whitespace.

        Args:
            title: Book title to search for.
            manifests_dir: Root directory that holds per-book manifest folders.

        Returns:
            :class:`~pathlib.Path` to the ``manifest.json`` file if found,
            otherwise ``None``.
        """
        root = Path(manifests_dir)
        if not root.is_dir():
            return None
        normalised = " ".join(title.lower().split())
        for candidate in sorted(root.rglob(MANIFEST_FILENAME)):
            try:
                data = json.loads(candidate.read_text(encoding="utf-8"))
                candidate_title = " ".join(data.get("book", {}).get("title", "").lower().split())
                if candidate_title == normalised:
                    return candidate
            except (json.JSONDecodeError, OSError):
                continue
        return None


# ---------------------------------------------------------------------------
# AudioCache  (LRU via a JSON index file)
# ---------------------------------------------------------------------------

_CACHE_INDEX_FILE = "cache_index.json"


class AudioCache:
    """Disk-backed LRU cache for TTS-generated audio segments.

    Cache entries are keyed by an MD5 digest of ``(text, voice, engine,
    speed)`` and stored as individual audio files inside *cache_dir*.  A
    lightweight JSON index tracks metadata and access order so that least-
    recently-used entries can be evicted when the cache exceeds *max_size_mb*.

    Thread-safety is provided by a single instance-level :class:`threading.Lock`.
    """

    def __init__(self, cache_dir: str = DEFAULT_CACHE_DIR, max_size_mb: float = DEFAULT_MAX_CACHE_MB) -> None:
        """Initialise the cache, loading an existing index if present.

        Args:
            cache_dir: Directory used for audio files and the index.
            max_size_mb: Soft maximum total cache size in megabytes.  Entries
                are evicted (oldest-accessed first) whenever this limit is
                exceeded after a ``put`` call.
        """
        self.cache_dir = Path(cache_dir)
        self.max_size_bytes = int(max_size_mb * 1024 * 1024)
        self._lock = threading.Lock()
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._index: dict[str, dict[str, Any]] = self._load_index()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get(self, text: str, voice: str, engine: str, speed: float = 1.0) -> str | None:
        """Return the cached audio file path for the given parameters, or None.

        Touching an entry updates its ``last_accessed`` timestamp for LRU
        purposes.

        Args:
            text: The text that was synthesised.
            voice: Voice identifier string.
            engine: TTS engine name (e.g. ``"edge-tts"``).
            speed: Playback speed multiplier.

        Returns:
            Absolute path string to the cached ``.mp3`` / ``.wav`` file, or
            ``None`` if the entry is absent or the file has been deleted.
        """
        key = self._make_key(text, voice, engine, speed)
        with self._lock:
            entry = self._index.get(key)
            if entry is None:
                return None
            file_path = Path(entry["file_path"])
            if not file_path.exists():
                del self._index[key]
                self._save_index()
                return None
            entry["last_accessed"] = _utcnow_iso()
            entry["access_count"] = entry.get("access_count", 0) + 1
            self._save_index()
            return str(file_path)

    def put(
        self,
        text: str,
        voice: str,
        engine: str,
        speed: float,
        audio_path: str,
        duration: float,
    ) -> str:
        """Register *audio_path* in the cache and return the canonical cache path.

        If *audio_path* is already inside ``cache_dir`` it is used in-place;
        otherwise the file is copied into ``cache_dir``.  The cache is then
        checked for size and LRU eviction is performed if necessary.

        Args:
            text: The text that was synthesised.
            voice: Voice identifier string.
            engine: TTS engine name.
            speed: Playback speed multiplier.
            audio_path: Path to the generated audio file to cache.
            duration: Duration of the audio in seconds.

        Returns:
            Absolute path string to the file inside the cache directory.
        """
        key = self._make_key(text, voice, engine, speed)
        src = Path(audio_path)
        suffix = src.suffix or ".mp3"
        dest = self.cache_dir / f"{key}{suffix}"

        with self._lock:
            if src.resolve() != dest.resolve():
                shutil.copy2(str(src), str(dest))
            now = _utcnow_iso()
            self._index[key] = {
                "key": key,
                "file_path": str(dest),
                "voice": voice,
                "engine": engine,
                "speed": speed,
                "duration_seconds": duration,
                "text_preview": text[:120],
                "created": now,
                "last_accessed": now,
                "access_count": 1,
                "size_bytes": dest.stat().st_size,
            }
            self._save_index()
            self._enforce_size_limit()
        return str(dest)

    def clear_all(self) -> None:
        """Remove all cached audio files and reset the index."""
        with self._lock:
            for entry in self._index.values():
                fp = Path(entry["file_path"])
                fp.unlink(missing_ok=True)
            self._index.clear()
            self._save_index()

    def get_stats(self) -> dict[str, Any]:
        """Return aggregate statistics about the cache.

        Returns:
            Dict with keys: ``total_files``, ``total_size_mb``,
            ``oldest_entry``, ``newest_entry``, ``total_duration_seconds``.
        """
        with self._lock:
            entries = list(self._index.values())
        if not entries:
            return {
                "total_files": 0,
                "total_size_mb": 0.0,
                "oldest_entry": None,
                "newest_entry": None,
                "total_duration_seconds": 0.0,
            }
        total_bytes = sum(e.get("size_bytes", 0) for e in entries)
        total_dur = sum(e.get("duration_seconds", 0.0) for e in entries)
        dates = [e["created"] for e in entries if e.get("created")]
        return {
            "total_files": len(entries),
            "total_size_mb": round(total_bytes / (1024 * 1024), 4),
            "oldest_entry": min(dates) if dates else None,
            "newest_entry": max(dates) if dates else None,
            "total_duration_seconds": round(total_dur, 2),
        }

    def get_manifest_stats(self, manifest: dict[str, Any]) -> dict[str, Any]:
        """Return per-chapter cache hit/miss statistics for *manifest*.

        For each chapter this returns how many of its segments already have a
        valid cache file versus how many still need to be generated.

        Args:
            manifest: A manifest dict (need not be the same one backing this
                cache instance).

        Returns:
            Dict mapping chapter index (int) to a sub-dict with keys
            ``title``, ``cached``, ``pending``, ``error``, ``total``.
        """
        result: dict[int, dict[str, Any]] = {}
        for chapter in manifest.get("chapters", []):
            ci = chapter["index"]
            stats: dict[str, Any] = {
                "title": chapter.get("title", f"Chapter {ci}"),
                "cached": 0,
                "pending": 0,
                "error": 0,
                "total": len(chapter.get("segments", [])),
            }
            for seg in chapter.get("segments", []):
                s = seg.get("status", STATUS_PENDING)
                if s == STATUS_CACHED:
                    stats["cached"] += 1
                elif s == STATUS_ERROR:
                    stats["error"] += 1
                else:
                    stats["pending"] += 1
            result[ci] = stats
        return result

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _make_key(text: str, voice: str, engine: str, speed: float) -> str:
        """Compute a stable MD5 hex digest for the given TTS parameters.

        Args:
            text: Source text.
            voice: Voice identifier.
            engine: Engine name.
            speed: Speed multiplier, normalised to 4 decimal places.

        Returns:
            32-character lowercase hex string.
        """
        normalised = f"{text}\x00{voice}\x00{engine}\x00{speed:.4f}"
        return hashlib.md5(normalised.encode("utf-8")).hexdigest()

    def _enforce_size_limit(self) -> None:
        """Evict the least-recently-used entries until the cache fits within the limit.

        Must be called with ``self._lock`` already held.
        """
        while True:
            total = sum(e.get("size_bytes", 0) for e in self._index.values())
            if total <= self.max_size_bytes:
                break
            if not self._index:
                break
            # Find the entry with the oldest last_accessed timestamp.
            lru_key = min(
                self._index,
                key=lambda k: self._index[k].get("last_accessed", ""),
            )
            entry = self._index.pop(lru_key)
            Path(entry["file_path"]).unlink(missing_ok=True)
        self._save_index()

    def _load_index(self) -> dict[str, dict[str, Any]]:
        """Load the JSON index from disk, returning an empty dict on any error."""
        index_path = self.cache_dir / _CACHE_INDEX_FILE
        if not index_path.exists():
            return {}
        try:
            return json.loads(index_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}

    def _save_index(self) -> None:
        """Persist the current in-memory index to disk atomically."""
        index_path = self.cache_dir / _CACHE_INDEX_FILE
        tmp = index_path.with_suffix(".tmp")
        try:
            tmp.write_text(json.dumps(self._index, indent=2, ensure_ascii=False), encoding="utf-8")
            tmp.replace(index_path)
        except OSError:
            tmp.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# EstimationEngine
# ---------------------------------------------------------------------------

_RATE_HISTORY_KEY = "_estimation_rates"
_FALLBACK_SECONDS_PER_SEGMENT: dict[str, float] = {
    "edge-tts": 0.8,
    "kokoro": 1.2,
    "default": 1.0,
}


class EstimationEngine:
    """Estimate TTS generation time for a manifest.

    Rates (seconds-per-segment) are stored inside the manifest under a
    private key so they survive restarts without needing an external
    database.

    Args:
        manifest: The manifest dict this engine is associated with.
    """

    def __init__(self, manifest: dict[str, Any]) -> None:
        self._manifest = manifest
        if _RATE_HISTORY_KEY not in manifest:
            manifest[_RATE_HISTORY_KEY] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def update_rate(self, actual_seconds: float, segment_count: int) -> None:
        """Record observed generation performance.

        Uses an exponential moving average (α = 0.3) to blend the new
        measurement with the historical rate so that recent performance
        weighs more than old measurements.

        Args:
            actual_seconds: Wall-clock time taken to generate *segment_count*
                segments.
            segment_count: Number of segments processed in *actual_seconds*.
        """
        if segment_count <= 0 or actual_seconds < 0:
            return
        engine = self._manifest.get("settings", {}).get("tts_engine", "default")
        new_rate = actual_seconds / segment_count
        store = self._manifest[_RATE_HISTORY_KEY]
        old_rate = store.get(engine)
        if old_rate is None:
            store[engine] = new_rate
        else:
            alpha = 0.3
            store[engine] = alpha * new_rate + (1.0 - alpha) * old_rate

    def estimate(self, pending_segments: int) -> float:
        """Return the estimated remaining generation time in seconds.

        Falls back to a conservative default if no historical data exists.

        Args:
            pending_segments: Number of segments not yet cached.

        Returns:
            Estimated seconds as a float.
        """
        engine = self._manifest.get("settings", {}).get("tts_engine", "default")
        store = self._manifest.get(_RATE_HISTORY_KEY, {})
        rate = store.get(engine) or _FALLBACK_SECONDS_PER_SEGMENT.get(
            engine, _FALLBACK_SECONDS_PER_SEGMENT["default"]
        )
        return round(rate * max(0, pending_segments), 2)

    def refresh_manifest_estimate(self) -> None:
        """Compute and write the ``estimated_remaining_seconds`` field into the manifest."""
        stats = ManifestManager.get_stats(self._manifest)
        pending = stats["pending_segments"]
        estimate = self.estimate(pending)
        self._manifest["progress"]["estimated_remaining_seconds"] = estimate


# ---------------------------------------------------------------------------
# GenerationSession  (context manager)
# ---------------------------------------------------------------------------

class GenerationSession:
    """Context manager that wraps a manifest + cancel event for one generation run.

    Usage::

        with GenerationSession(manifest, manifest_path) as session:
            for ci, si in session.pending:
                if session.cancelled:
                    break
                # … generate segment …
                session.record_segment(ci, si, cache_file, duration, STATUS_CACHED)
                session.report_progress()

    The session records wall-clock start time on enter, marks
    ``generation_started`` in the manifest, and saves the manifest on both
    clean exit and exception.

    Args:
        manifest: The manifest dict to operate on.
        manifest_path: Path where ``manifest.json`` should be saved.
        cancel_event: Optional external :class:`threading.Event`; a new one is
            created if *None*.
        estimation_engine: Optional :class:`EstimationEngine`; created
            automatically if *None*.
        progress_callback: Optional callable ``(stats: dict) -> None`` invoked
            after each :meth:`report_progress` call.
    """

    def __init__(
        self,
        manifest: dict[str, Any],
        manifest_path: str | Path,
        cancel_event: threading.Event | None = None,
        estimation_engine: EstimationEngine | None = None,
        progress_callback=None,
    ) -> None:
        self.manifest = manifest
        self.manifest_path = Path(manifest_path)
        self.cancel_event: threading.Event = cancel_event or threading.Event()
        self.estimation_engine: EstimationEngine = estimation_engine or EstimationEngine(manifest)
        self.progress_callback = progress_callback

        self._start_time: float = 0.0
        self._segments_this_session: int = 0
        self._active: bool = False

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------

    def __enter__(self) -> "GenerationSession":
        self._start_time = time.monotonic()
        self._active = True
        self.manifest["progress"]["generation_started"] = _utcnow_iso()
        ManifestManager.save(self.manifest, self.manifest_path)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        self._active = False
        self._flush_timing()
        try:
            ManifestManager.save(self.manifest, self.manifest_path)
        except OSError:
            pass
        return False  # do not suppress exceptions

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------

    @property
    def cancelled(self) -> bool:
        """True if the external cancel event has been set."""
        return self.cancel_event.is_set()

    def cancel(self) -> None:
        """Signal cancellation."""
        self.cancel_event.set()

    @property
    def pending(self) -> list[tuple[int, int]]:
        """Return incomplete (chapter_idx, seg_idx) pairs from the manifest."""
        return ManifestManager.find_incomplete(self.manifest)

    def record_segment(
        self,
        chapter_idx: int,
        seg_idx: int,
        cache_file: str | None,
        duration: float | None,
        status: str,
    ) -> None:
        """Update a segment in the manifest and increment the session counter.

        Args:
            chapter_idx: Zero-based chapter index.
            seg_idx: Zero-based segment index.
            cache_file: Path to cached audio file, or ``None``.
            duration: Audio duration in seconds, or ``None``.
            status: New segment status string.
        """
        ManifestManager.update_segment(
            self.manifest, chapter_idx, seg_idx, cache_file, duration, status
        )
        if status == STATUS_CACHED:
            self._segments_this_session += 1

    def report_progress(self) -> dict[str, Any]:
        """Compute current stats, update the estimation, and invoke callback.

        Returns:
            The stats dict as returned by :meth:`ManifestManager.get_stats`.
        """
        self.estimation_engine.refresh_manifest_estimate()
        stats = ManifestManager.get_stats(self.manifest)
        if self.progress_callback is not None:
            try:
                self.progress_callback(stats)
            except Exception:  # noqa: BLE001
                pass
        return stats

    def elapsed_seconds(self) -> float:
        """Return the number of seconds since the session started."""
        return time.monotonic() - self._start_time

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _flush_timing(self) -> None:
        """Persist observed generation rate into the estimation engine."""
        elapsed = self.elapsed_seconds()
        if self._segments_this_session > 0 and elapsed > 0:
            self.estimation_engine.update_rate(elapsed, self._segments_this_session)


# ---------------------------------------------------------------------------
# Pipeline stage stubs
# ---------------------------------------------------------------------------

def stage_parse(
    input_path: str,
    settings: dict[str, Any],
    progress_callback=None,
) -> dict[str, Any]:
    """Stage 1: Parse the source book into a structured manifest.

    Delegates to the ``text_processor`` module (merged in the combined app).
    After parsing, the manifest is saved to ``manifests/<title>/manifest.json``
    and returned.

    Args:
        input_path: Path or URL of the source book.
        settings: User-supplied settings dict; merged with defaults.
        progress_callback: Optional callable ``(msg: str, pct: float) -> None``
            invoked as chapters are parsed.

    Returns:
        A fully-populated manifest dict with chapters and segments filled in.

    Note:
        This stub will be replaced when the text-processor module is merged
        into the single-file application.
    """
    pass  # Will be filled when modules are merged


def stage_generate(
    manifest: dict[str, Any],
    cancel_event: threading.Event,
    progress_callback=None,
) -> dict[str, Any]:
    """Stage 2: Synthesise audio for all pending segments.

    Iterates over incomplete segments (as reported by
    :meth:`ManifestManager.find_incomplete`) and calls the configured TTS
    engine for each one.  Completed segments are written to the LRU cache and
    the manifest is updated after each segment.  Generation can be interrupted
    at any segment boundary by setting *cancel_event*.

    Args:
        manifest: A manifest dict, typically the output of :func:`stage_parse`
            or a partially-completed manifest loaded from disk.
        cancel_event: Setting this event at any time cleanly stops generation
            after the current segment finishes.
        progress_callback: Optional callable ``(stats: dict) -> None`` invoked
            after each segment is cached.

    Returns:
        The updated manifest dict.

    Note:
        This stub will be replaced when the TTS-engine module is merged.
    """
    pass  # Will be filled when modules are merged


def stage_assemble(
    manifest: dict[str, Any],
    progress_callback=None,
) -> str:
    """Stage 3: Assemble cached audio segments into the final audiobook file.

    Reads ``cache_file`` paths from each segment in chapter order, concatenates
    them, optionally ducks background music, and writes the output to
    ``output/<title>.<format>`` as specified by ``manifest["settings"]``.

    Args:
        manifest: A manifest dict whose segments all have status ``"cached"``.
        progress_callback: Optional callable ``(msg: str, pct: float) -> None``
            invoked as chapters are assembled.

    Returns:
        Absolute path to the finished audiobook file.

    Note:
        This stub will be replaced when the audio-processor module is merged.
    """
    pass  # Will be filled when modules are merged


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------

def _utcnow_iso() -> str:
    """Return the current UTC time as an ISO-8601 string with timezone suffix."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
