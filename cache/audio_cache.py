from __future__ import annotations

import contextlib
import hashlib
import json
import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional


@dataclass
class AudioCacheDeps:
    atomic_json_write_fn: Callable[[Path, dict[str, Any], bool], None]
    advisory_file_lock_fn: Callable[[Path], Any]
    file_sha256_fn: Callable[[str | Path], str]
    get_duration_ffprobe_fn: Callable[[str], float]
    cache_key_schema_version: int


class AudioCache:
    def __init__(self, cache_dir: str | Path, max_size_mb: int, deps: AudioCacheDeps):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.max_size_bytes = max_size_mb * 1024 * 1024
        self.index_path = self.cache_dir / "cache_index.json"
        self.lock_path = self.cache_dir / ".cache_index.lock"
        self.deps = deps
        self.index = self._load_index()
        self.repair_index()

    def _load_index(self) -> dict[str, dict[str, Any]]:
        with self.deps.advisory_file_lock_fn(self.lock_path):
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
        with self.deps.advisory_file_lock_fn(self.lock_path):
            self.deps.atomic_json_write_fn(self.index_path, self.index, keep_backup=True)

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
        material = (
            f"v={self.deps.cache_key_schema_version}|{text}|{voice}|{engine}|"
            f"{effective_speed}|{pronunciation_hash}|{speed_mode}"
        )
        return hashlib.md5(material.encode("utf-8")).hexdigest()

    def _is_cache_entry_valid(self, path: Path, entry: dict[str, Any]) -> bool:
        if not path.exists() or path.stat().st_size <= 0:
            return False
        expected_duration = float(entry.get("duration", 0.0) or 0.0)
        actual_duration = self.deps.get_duration_ffprobe_fn(str(path))
        if actual_duration <= 0:
            return False
        if expected_duration > 0 and abs(actual_duration - expected_duration) > 0.75:
            return False
        expected_sha = str(entry.get("sha256", "") or "")
        if expected_sha:
            with contextlib.suppress(Exception):
                if self.deps.file_sha256_fn(path) != expected_sha:
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
        sha = self.deps.file_sha256_fn(cache_path) if cache_path.exists() else ""
        self.index[key] = {
            "filename": cache_filename,
            "voice": voice,
            "engine": engine,
            "duration": float(duration),
            "size_bytes": size,
            "sha256": sha,
            "key_schema_version": self.deps.cache_key_schema_version,
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
