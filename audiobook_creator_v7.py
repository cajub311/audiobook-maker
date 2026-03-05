#!/usr/bin/env python3
"""
Audiobook Creator V7
====================
Convert EPUB, PDF, TXT books or web pages into fully-chaptered M4B/MP3 audiobooks
with per-character voices, pronunciation overrides, and loudness normalization.

Usage:
    python audiobook_creator_v7.py              # Gradio UI at http://localhost:7860
    python audiobook_creator_v7.py --share       # Public Gradio link
    python audiobook_creator_v7.py --port 8080   # Custom port

Architecture: 3-stage manifest pipeline
  Stage 1 – Parse:    Book → manifest.json (chapters, segments, cache status)
  Stage 2 – Generate: manifest → per-segment MP3 files (TTS + cache)
  Stage 3 – Assemble: cache files → final .m4b / .mp3 (concat + normalize)

Target machine: Windows/Linux, 2-4 cores, 3–8 GB RAM
"""

from __future__ import annotations

import argparse
import asyncio
import gc
import hashlib
import json
import logging
import os
import shutil
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, Generator, Optional

# ---------------------------------------------------------------------------
# Module imports (each src_*.py is a logical section of this single-file app)
# ---------------------------------------------------------------------------

from src_manifest import (
    ManifestManager,
    AudioCache,
    GenerationSession,
    EstimationEngine,
    RetryPolicy,
    MANIFEST_FILENAME,
    MANIFESTS_DIR,
    STATUS_CACHED,
    STATUS_ERROR,
    STATUS_PENDING,
    SEGMENT_SCENE_BREAK,
    SEGMENT_DIALOGUE,
    SEGMENT_SFX,
    SEGMENT_NARRATION,
)

from src_tts_audio import (
    TTSEngineFactory,
    generate_silence,
    concat_audio_files,
    normalize_loudness,
    mix_with_background_music,
    encode_to_m4b,
    generate_chapter_metadata_file,
    generate_batch,
    SilenceCache,
    get_duration_ffprobe,
    adjust_speed_atempo,
    _get_silence_cache,
)

from src_text_processor import (
    yield_chapters,
    chunk_text_smart,
    detect_all_dialogue,
    CharacterRegistry,
    PronunciationDict,
    analyze_book,
    clean_text_for_tts,
    detect_emotion,
    apply_ssml_hints,
    detect_scene_breaks,
)

from src_ui import build_ui, launch_app

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("audiobook_v7")

# ---------------------------------------------------------------------------
# Global cache / singleton
# ---------------------------------------------------------------------------

_audio_cache: Optional[AudioCache] = None


def get_cache() -> AudioCache:
    global _audio_cache
    if _audio_cache is None:
        _audio_cache = AudioCache()
    return _audio_cache


# ===========================================================================
# STAGE 1: Parse — Book → Manifest
# ===========================================================================

def stage_parse(
    input_path: str,
    settings: dict[str, Any],
    progress_callback=None,
) -> dict[str, Any]:
    """Parse a book file/URL/text into a fully-populated manifest.

    Args:
        input_path: File path, URL, or raw text content.
        settings: User settings dict merged with defaults.
        progress_callback: Optional ``(msg: str, pct: float) -> None``.

    Returns:
        A manifest dict saved to ``manifests/<title>/manifest.json``.
    """
    def _cb(msg: str, pct: float = 0.0):
        log.info("[parse] %.0f%% — %s", pct * 100, msg)
        if progress_callback:
            progress_callback(msg, pct)

    _cb("Initialising manifest …", 0.0)
    manifest = ManifestManager.create(input_path, settings)

    engine_id = settings.get("tts_engine", "edge-tts")
    narrator_voice = settings.get("narrator_voice", "en-US-GuyNeural")
    dialogue_voice = settings.get("dialogue_voice", "en-US-JennyNeural")
    char_voices: dict[str, dict] = settings.get("character_voices", {})
    pronunciations = PronunciationDict(settings.get("pronunciation_overrides", {}))
    cache = get_cache()

    # Build available voice pool from settings
    voice_pool = [narrator_voice, dialogue_voice] + [
        cv["voice"] for cv in char_voices.values() if "voice" in cv
    ]

    registry = CharacterRegistry(voice_pool)
    # Pre-seed known character voices from settings
    for char_name, cv_info in char_voices.items():
        if "voice" in cv_info:
            registry.assign_voice(char_name, cv_info["voice"])

    chapters_raw: list[dict] = []
    chapter_list: list[dict] = []
    total_segments = 0
    chapter_gen = list(yield_chapters(input_path))
    chapter_count = len(chapter_gen)

    for ch_idx, chapter_raw in enumerate(chapter_gen):
        _cb(f"Parsing chapter {ch_idx + 1}/{chapter_count}: {chapter_raw['title']}", ch_idx / max(chapter_count, 1))
        chapters_raw.append(chapter_raw)
        chapter_text = chapter_raw["text"]

        # Detect dialogue and build attributed quote map
        dialogue_results = detect_all_dialogue(chapter_text)
        dialogue_map: dict[tuple, str] = {
            (d["start"], d["end"]): d.get("speaker") or "narrator"
            for d in dialogue_results
            if d.get("speaker")
        }

        # Register characters with registry
        for d in dialogue_results:
            if d.get("speaker") and d["speaker"] != "narrator":
                registry.register(d["speaker"], d.get("method", "unknown"))

        # Detect scene breaks in this chapter
        scene_break_positions = set(detect_scene_breaks(chapter_text))

        # Chunk the chapter text into TTS-sized segments
        chunks = chunk_text_smart(chapter_text, max_chars=5500)
        segments: list[dict] = []

        char_offset = 0
        for seg_idx, chunk in enumerate(chunks):
            raw_text = chunk["text"]
            seg_type = chunk.get("segment_type", SEGMENT_NARRATION)

            # Determine speaker: check if this chunk overlaps a dialogue span
            speaker = "narrator"
            for (d_start, d_end), d_speaker in dialogue_map.items():
                if d_start <= char_offset <= d_end:
                    speaker = d_speaker
                    break

            voice = narrator_voice
            if speaker != "narrator":
                voice = registry.get_voice(speaker) or dialogue_voice

            # Apply pronunciation overrides to get the text for TTS
            tts_text = clean_text_for_tts(pronunciations.apply(raw_text))

            # Optionally wrap with SSML hints
            emotion = detect_emotion(raw_text)
            if emotion != "normal":
                voice_type = "dialogue" if speaker != "narrator" else "narration"
                tts_text = apply_ssml_hints(tts_text, emotion, voice_type)

            # Generate cache key and check if already cached
            cache_key = hashlib.md5(
                f"{tts_text}|{voice}|{engine_id}|{settings.get('speed_multiplier', 1.0)}".encode()
            ).hexdigest()
            cached_path = cache.get(tts_text, voice, engine_id, settings.get("speed_multiplier", 1.0))
            seg_status = STATUS_CACHED if cached_path else STATUS_PENDING

            segments.append({
                "index": seg_idx,
                "text": raw_text,
                "tts_text": tts_text,
                "text_hash": cache_key,
                "speaker": speaker,
                "voice": voice,
                "cache_file": cached_path,
                "duration_seconds": get_duration_ffprobe(cached_path) if cached_path else None,
                "status": seg_status,
                "segment_type": seg_type,
                "is_scene_break": chunk.get("is_scene_break", False),
                "paragraph_end": chunk.get("paragraph_end", False),
            })
            char_offset += len(raw_text)

        chapter_list.append({
            "index": ch_idx,
            "title": chapter_raw["title"],
            "status": "complete" if all(s["status"] == STATUS_CACHED for s in segments) else STATUS_PENDING,
            "segments": segments,
        })
        total_segments += len(segments)

        del chapter_text, chunks
        gc.collect()

    # Auto-assign voices for any newly registered characters
    registry.auto_assign_voices()

    # Write character voice assignments back into manifest settings
    manifest["settings"]["character_voices"] = {
        name: {"voice": registry.get_voice(name), "detected_by": "auto"}
        for name in registry.to_dict()
    }
    manifest["chapters"] = chapter_list
    manifest["progress"]["total_segments"] = total_segments
    manifest["progress"]["completed_segments"] = sum(
        1 for ch in chapter_list for s in ch["segments"] if s["status"] == STATUS_CACHED
    )

    # Run book-level analysis
    manifest["_analysis"] = analyze_book(chapters_raw)

    # Estimate generation time
    estimator = EstimationEngine(engine_id)
    pending = manifest["progress"]["total_segments"] - manifest["progress"]["completed_segments"]
    manifest["progress"]["estimated_remaining_seconds"] = estimator.estimate(pending)

    # Save manifest to disk
    manifest_dir = Path(MANIFESTS_DIR) / _safe_title(manifest["book"]["title"])
    manifest_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = manifest_dir / MANIFEST_FILENAME
    ManifestManager.save(manifest, str(manifest_path))

    _cb(f"Parse complete — {total_segments} segments, {len(chapter_list)} chapters", 1.0)
    return manifest


# ===========================================================================
# STAGE 2: Generate — Manifest → Audio Segments
# ===========================================================================

def stage_generate(
    manifest: dict[str, Any],
    cancel_event: threading.Event,
    progress_callback=None,
) -> dict[str, Any]:
    """Synthesise audio for all pending segments.

    Iterates incomplete segments in chapter order and calls the configured
    TTS engine.  The manifest is saved after every segment so the job can be
    resumed at any time.

    Args:
        manifest: Manifest dict (from stage_parse or loaded from disk).
        cancel_event: Set this to cleanly stop after the current segment.
        progress_callback: Optional ``(stats: dict) -> None``.

    Returns:
        Updated manifest dict with all segments set to ``"cached"``.
    """
    engine_id = manifest["settings"].get("tts_engine", "edge-tts")
    speed = manifest["settings"].get("speed_multiplier", 1.0)
    engine = TTSEngineFactory.get(engine_id)
    cache = get_cache()

    retry = RetryPolicy(max_retries=3, backoff_seconds=2.0, jitter=True)

    manifest_dir = Path(MANIFESTS_DIR) / _safe_title(manifest["book"]["title"])
    manifest_path = manifest_dir / MANIFEST_FILENAME

    incomplete = ManifestManager.find_incomplete(manifest)
    total_pending = len(incomplete)
    log.info("[generate] %d segments pending synthesis", total_pending)

    with GenerationSession(manifest, cancel_event) as session:
        for done_count, (ch_idx, seg_idx) in enumerate(incomplete):
            if cancel_event.is_set():
                log.info("[generate] Cancelled after %d segments", done_count)
                break

            chapter = manifest["chapters"][ch_idx]
            segment = chapter["segments"][seg_idx]
            tts_text = segment.get("tts_text") or segment["text"]
            voice = segment["voice"]

            log.debug("[generate] ch%d seg%d voice=%s", ch_idx, seg_idx, voice)

            # --- TTS synthesis with retry ---
            temp_path = Path("temp") / f"seg_{ch_idx}_{seg_idx}.mp3"
            temp_path.parent.mkdir(parents=True, exist_ok=True)

            try:
                async def _gen():
                    return await engine.generate(
                        text=tts_text,
                        voice=voice,
                        speed=speed,
                        output_path=str(temp_path),
                    )

                result = retry.execute(lambda: asyncio.run(_gen()))
                duration = result.duration_seconds

                cache_path = cache.put(
                    text=tts_text,
                    voice=voice,
                    engine=engine_id,
                    speed=speed,
                    audio_path=str(temp_path),
                    duration=duration,
                )

                ManifestManager.update_segment(
                    manifest, ch_idx, seg_idx,
                    cache_file=cache_path,
                    duration=duration,
                    status=STATUS_CACHED,
                )
                session.record_segment(duration)

            except Exception as exc:
                log.error("[generate] ch%d seg%d FAILED: %s", ch_idx, seg_idx, exc)
                ManifestManager.update_segment(
                    manifest, ch_idx, seg_idx,
                    cache_file=None, duration=None, status=STATUS_ERROR,
                )
            finally:
                if temp_path.exists():
                    temp_path.unlink(missing_ok=True)

            ManifestManager.save(manifest, str(manifest_path))

            stats = ManifestManager.get_stats(manifest)
            stats["current_chapter"] = chapter["title"]
            stats["current_segment"] = seg_idx
            if progress_callback:
                progress_callback(stats)

            pct = (done_count + 1) / max(total_pending, 1)
            log.info("[generate] %.0f%% — ch%d seg%d done", pct * 100, ch_idx, seg_idx)

    return manifest


# ===========================================================================
# STAGE 3: Assemble — Audio Segments → Final Audiobook
# ===========================================================================

def stage_assemble(
    manifest: dict[str, Any],
    progress_callback=None,
) -> str:
    """Assemble cached segments into a final audiobook file.

    Builds an FFmpeg concat list with silence gaps, optionally mixes background
    music, normalises loudness, and encodes to M4B or MP3.

    Args:
        manifest: Manifest with all segments at ``"cached"`` status.
        progress_callback: Optional ``(msg: str, pct: float) -> None``.

    Returns:
        Absolute path to the finished audiobook file.
    """
    def _cb(msg: str, pct: float = 0.0):
        log.info("[assemble] %.0f%% — %s", pct * 100, msg)
        if progress_callback:
            progress_callback(msg, pct)

    settings = manifest["settings"]
    title = manifest["book"]["title"]
    output_format = settings.get("output_format", "m4b").lower()
    normalize = settings.get("normalize", True)
    bg_music_path = settings.get("background_music")
    music_duck_db = settings.get("music_duck_db", -15)

    temp_dir = Path("temp") / _safe_title(title)
    temp_dir.mkdir(parents=True, exist_ok=True)
    output_dir = Path("output")
    output_dir.mkdir(parents=True, exist_ok=True)

    silence_cache = _get_silence_cache()

    # --- Build ordered list of audio files with silence gaps ---
    _cb("Building segment list …", 0.05)
    audio_files: list[str] = []

    chapter_count = len(manifest["chapters"])
    for ch_idx, chapter in enumerate(manifest["chapters"]):
        for seg_idx, segment in enumerate(chapter["segments"]):
            if segment["status"] != STATUS_CACHED or not segment.get("cache_file"):
                log.warning("[assemble] Skipping un-cached segment ch%d seg%d", ch_idx, seg_idx)
                continue

            audio_files.append(segment["cache_file"])

            # Silence after segment
            seg_type = segment.get("segment_type", SEGMENT_NARRATION)
            if segment.get("is_scene_break"):
                sil = silence_cache.get(1.0)
            elif segment.get("paragraph_end"):
                sil = silence_cache.get(0.5)
            elif seg_type == SEGMENT_DIALOGUE:
                sil = silence_cache.get(0.3)
            else:
                sil = silence_cache.get(0.3)
            audio_files.append(sil)

        # Chapter break silence (except after last chapter)
        if ch_idx < chapter_count - 1:
            audio_files.append(silence_cache.get(2.0))

    # --- Concatenate ---
    _cb("Concatenating segments …", 0.2)
    concat_path = str(temp_dir / "concatenated.mp3")
    concat_audio_files(audio_files, concat_path)

    # --- Mix background music ---
    mixed_path = concat_path
    if bg_music_path and Path(bg_music_path).exists():
        _cb("Mixing background music …", 0.5)
        mixed_path = str(temp_dir / "mixed.mp3")
        mix_with_background_music(concat_path, bg_music_path, mixed_path, music_duck_db)

    # --- Loudness normalisation ---
    normalised_path = mixed_path
    if normalize:
        _cb("Normalising loudness (two-pass EBU R128, −19 LUFS) …", 0.65)
        normalised_path = str(temp_dir / "normalized.mp3")
        normalize_loudness(mixed_path, normalised_path, target_lufs=-19.0)

    # --- Encode to final format ---
    safe_title = _safe_title(title)
    final_path = str(output_dir / f"{safe_title}.{output_format}")

    if output_format == "m4b":
        _cb("Generating chapter metadata …", 0.80)
        meta_path = str(temp_dir / "chapters_meta.txt")
        generate_chapter_metadata_file(manifest, meta_path)

        _cb("Encoding to M4B …", 0.88)
        book_meta = {
            "title": title,
            "author": manifest["book"].get("author", ""),
            "album": title,
            "genre": "Audiobook",
        }
        cover_path = settings.get("cover_art_path")
        final_path = encode_to_m4b(
            mp3_path=normalised_path,
            metadata=book_meta,
            chapters_meta_path=meta_path,
            cover_art_path=cover_path if cover_path and Path(cover_path or "").exists() else None,
            output_path=final_path,
        )
    else:
        # MP3: just move the normalised file
        shutil.copy2(normalised_path, final_path)

    _cb(f"Audiobook ready → {final_path}", 1.0)
    return str(Path(final_path).resolve())


# ===========================================================================
# Helpers
# ===========================================================================

def _safe_title(title: str) -> str:
    """Return a filesystem-safe version of a book title."""
    safe = "".join(c if c.isalnum() or c in " _-" else "_" for c in title)
    return safe.strip().replace(" ", "_")[:80] or "untitled"


# ===========================================================================
# Patch UI module with real pipeline implementations
# ===========================================================================

def _patch_ui_handlers():
    """
    Inject the real stage functions into src_ui so its event handlers
    call the fully-wired pipeline instead of stubs.
    """
    import src_ui as ui_module
    ui_module._STAGE_PARSE = stage_parse
    ui_module._STAGE_GENERATE = stage_generate
    ui_module._STAGE_ASSEMBLE = stage_assemble
    ui_module._GET_CACHE = get_cache


# ===========================================================================
# Entry Point
# ===========================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Audiobook Creator V7 — convert books to chaptered M4B/MP3 audiobooks"
    )
    parser.add_argument("--share", action="store_true", help="Create a public Gradio share link")
    parser.add_argument("--port", type=int, default=7860, help="Gradio server port (default: 7860)")
    parser.add_argument("--api-port", type=int, default=7861, help="REST API port (default: 7861)")
    parser.add_argument("--no-api", action="store_true", help="Disable the FastAPI REST endpoint")
    args = parser.parse_args()

    # Wire real pipeline into UI
    _patch_ui_handlers()

    # Ensure directories exist
    for d in ["tts_cache", "manifests", "temp", "output", "pronunciations"]:
        Path(d).mkdir(exist_ok=True)

    log.info("Starting Audiobook Creator V7 …")
    log.info("  Gradio UI  → http://localhost:%d", args.port)
    if not args.no_api:
        log.info("  REST API   → http://localhost:%d/docs", args.api_port)

    launch_app(
        share=args.share,
        port=args.port,
        api_port=args.api_port if not args.no_api else None,
    )


if __name__ == "__main__":
    main()
