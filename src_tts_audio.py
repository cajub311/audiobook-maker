"""
src_tts_audio.py — TTS engine implementations and FFmpeg audio processing utilities
for Audiobook Creator V7.

Engines:
  - EdgeTTSEngine  : Microsoft Edge TTS (requires internet, high concurrency)
  - KokoroEngine   : Kokoro ONNX offline TTS (no internet after model download)

Audio utilities (all via subprocess + FFmpeg/ffprobe):
  get_duration_ffprobe, generate_silence, concat_audio_files,
  normalize_loudness, mix_with_background_music, encode_to_m4b,
  generate_chapter_metadata_file, adjust_speed_atempo,
  detect_audio_issues

Additional helpers:
  SilenceCache     : reuse pre-generated silence files across the session
  generate_batch   : async semaphore-bounded batch TTS generation
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
import os
import re
import subprocess
import tempfile
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Core dataclass
# ---------------------------------------------------------------------------

@dataclass
class TTSResult:
    """Result returned by every TTS engine after synthesis."""
    audio_path: str
    duration_seconds: float
    sample_rate: int


# ---------------------------------------------------------------------------
# Abstract base class
# ---------------------------------------------------------------------------

class TTSEngine(ABC):
    """Abstract base for all TTS engines used by Audiobook Creator."""

    @abstractmethod
    async def generate(
        self,
        text: str,
        voice: str,
        speed: float = 1.0,
        output_path: str = None,
    ) -> TTSResult:
        """Synthesise *text* with *voice* and write to *output_path*.

        If *output_path* is None the engine must choose a temp path.
        Returns a :class:`TTSResult` with the final file path and metadata.
        """

    @abstractmethod
    def list_voices(self) -> list[dict]:
        """Return available voices as a list of dicts with standardised keys:
        ``id``, ``name``, ``gender``, ``locale``, ``engine``."""

    @abstractmethod
    async def preview(self, voice: str, sample_text: str = None) -> TTSResult:
        """Generate a short (~5 s) sample for the given voice."""

    @property
    @abstractmethod
    def max_concurrent(self) -> int:
        """Maximum number of simultaneous synthesis requests this engine supports."""

    @property
    @abstractmethod
    def requires_internet(self) -> bool:
        """True if the engine needs a live internet connection to function."""

    @property
    @abstractmethod
    def engine_id(self) -> str:
        """Short identifier used in configuration and factory lookup."""


# ---------------------------------------------------------------------------
# EdgeTTSEngine
# ---------------------------------------------------------------------------

_PREVIEW_TEXT = (
    "Welcome to the audiobook. This is a preview of the selected voice. "
    "I hope you enjoy listening."
)

_EXCLAMATION_RE = re.compile(r"!")
_QUESTION_RE    = re.compile(r"\?")


def _build_ssml(text: str) -> str:
    """Wrap plain text in SSML, adding moderate emphasis on sentences that
    end with '!' and a rising-intonation mark on sentences ending with '?'.
    """
    # Escape XML special characters before embedding in SSML.
    escaped = (
        text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
            .replace("'", "&apos;")
    )

    sentences: list[str] = []
    for sentence in re.split(r"(?<=[.!?])\s+", escaped):
        sentence = sentence.strip()
        if not sentence:
            continue
        if _EXCLAMATION_RE.search(sentence):
            sentences.append(f'<prosody rate="fast" pitch="+10%">{sentence}</prosody>')
        elif _QUESTION_RE.search(sentence):
            sentences.append(f'<prosody pitch="+5%">{sentence}</prosody>')
        else:
            sentences.append(sentence)

    body = " ".join(sentences)
    return (
        '<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" '
        'xml:lang="en-US">'
        f"<voice name=\"{{voice}}\"><p>{body}</p></voice>"
        "</speak>"
    )


class EdgeTTSEngine(TTSEngine):
    """Microsoft Edge TTS engine via the :mod:`edge_tts` package.

    Features:
    - SSML auto-detection and wrapping
    - Connection retries with exponential backoff (3 retries, 2 s base)
    - In-memory voice list cache (populated once per process)
    """

    _voice_cache: list[dict] | None = None  # class-level cache

    @property
    def max_concurrent(self) -> int:
        return 12

    @property
    def requires_internet(self) -> bool:
        return True

    @property
    def engine_id(self) -> str:
        return "edge-tts"

    # ------------------------------------------------------------------
    # Voice listing
    # ------------------------------------------------------------------

    def list_voices(self) -> list[dict]:
        """Return cached (or freshly fetched) list of Edge TTS voices."""
        if EdgeTTSEngine._voice_cache is not None:
            return EdgeTTSEngine._voice_cache

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # If already inside an async context, schedule a new one.
                future = asyncio.ensure_future(self._fetch_voices())
                # Caller must await; return empty list for now.
                logger.warning(
                    "list_voices() called from within a running event loop. "
                    "Use await engine.list_voices_async() instead."
                )
                return []
            return loop.run_until_complete(self._fetch_voices())
        except Exception:
            return loop.run_until_complete(self._fetch_voices())

    async def list_voices_async(self) -> list[dict]:
        """Async version of :meth:`list_voices`."""
        if EdgeTTSEngine._voice_cache is not None:
            return EdgeTTSEngine._voice_cache
        return await self._fetch_voices()

    async def _fetch_voices(self) -> list[dict]:
        import edge_tts  # lazy import

        raw: list[dict] = await edge_tts.list_voices()
        voices = [
            {
                "id":     v["ShortName"],
                "name":   v.get("FriendlyName", v["ShortName"]),
                "gender": v.get("Gender", "Unknown"),
                "locale": v.get("Locale", ""),
                "engine": self.engine_id,
            }
            for v in raw
        ]
        EdgeTTSEngine._voice_cache = voices
        logger.debug("EdgeTTS: loaded %d voices", len(voices))
        return voices

    # ------------------------------------------------------------------
    # Text preparation
    # ------------------------------------------------------------------

    def _prepare_text(self, text: str, voice: str) -> tuple[str, bool]:
        """Return *(final_text, is_ssml)*.

        If *text* is already wrapped in ``<ssml>`` tags it is passed through
        as SSML.  Otherwise, if the text contains '!' or '?', it is
        auto-wrapped in SSML with prosody hints.
        """
        stripped = text.strip()
        if stripped.lower().startswith("<ssml>") or stripped.startswith("<speak"):
            # Caller supplied raw SSML; honour it.
            inner = re.sub(r"(?i)^<ssml>\s*", "", stripped)
            inner = re.sub(r"\s*</ssml>$(?i)", "", inner)
            return inner, True

        if _EXCLAMATION_RE.search(text) or _QUESTION_RE.search(text):
            ssml = _build_ssml(text).replace("{voice}", voice)
            return ssml, True

        return text, False

    # ------------------------------------------------------------------
    # Generation
    # ------------------------------------------------------------------

    async def generate(
        self,
        text: str,
        voice: str,
        speed: float = 1.0,
        output_path: str = None,
    ) -> TTSResult:
        """Synthesise *text* and write MP3 to *output_path*."""
        import edge_tts  # lazy import

        if output_path is None:
            output_path = os.path.join(
                tempfile.gettempdir(), f"edge_tts_{uuid.uuid4().hex}.mp3"
            )

        # Speed → rate string: +10% means 10 % faster; –10% means 10 % slower.
        rate_pct = int(round((speed - 1.0) * 100))
        rate_str = f"+{rate_pct}%" if rate_pct >= 0 else f"{rate_pct}%"

        final_text, is_ssml = self._prepare_text(text, voice)

        retries = 3
        base_delay = 2.0

        for attempt in range(retries):
            try:
                communicate = edge_tts.Communicate(
                    final_text,
                    voice=voice,
                    rate=rate_str,
                )
                await communicate.save(output_path)
                break
            except Exception as exc:
                if attempt == retries - 1:
                    raise RuntimeError(
                        f"EdgeTTS generation failed after {retries} attempts: {exc}"
                    ) from exc
                delay = base_delay * (2 ** attempt)
                logger.warning(
                    "EdgeTTS attempt %d/%d failed (%s). Retrying in %.1fs…",
                    attempt + 1, retries, exc, delay,
                )
                await asyncio.sleep(delay)

        duration = get_duration_ffprobe(output_path)
        return TTSResult(audio_path=output_path, duration_seconds=duration, sample_rate=24000)

    # ------------------------------------------------------------------
    # Preview
    # ------------------------------------------------------------------

    async def preview(self, voice: str, sample_text: str = None) -> TTSResult:
        text = sample_text or _PREVIEW_TEXT
        return await self.generate(text, voice=voice, speed=1.0)


# ---------------------------------------------------------------------------
# KokoroEngine
# ---------------------------------------------------------------------------

_KOKORO_VOICES: list[dict] = [
    {"id": "af",       "name": "Kokoro Default (AF)",        "gender": "Female", "locale": "en-us", "engine": "kokoro"},
    {"id": "af_bella", "name": "Bella (AF)",                  "gender": "Female", "locale": "en-us", "engine": "kokoro"},
    {"id": "af_irulan","name": "Irulan (AF)",                  "gender": "Female", "locale": "en-us", "engine": "kokoro"},
    {"id": "af_jessica","name": "Jessica (AF)",               "gender": "Female", "locale": "en-us", "engine": "kokoro"},
    {"id": "af_kore",  "name": "Kore (AF)",                   "gender": "Female", "locale": "en-us", "engine": "kokoro"},
    {"id": "af_nicole","name": "Nicole (AF)",                  "gender": "Female", "locale": "en-us", "engine": "kokoro"},
    {"id": "af_nova",  "name": "Nova (AF)",                   "gender": "Female", "locale": "en-us", "engine": "kokoro"},
    {"id": "af_river", "name": "River (AF)",                  "gender": "Female", "locale": "en-us", "engine": "kokoro"},
    {"id": "af_sarah", "name": "Sarah (AF)",                  "gender": "Female", "locale": "en-us", "engine": "kokoro"},
    {"id": "af_sky",   "name": "Sky (AF)",                    "gender": "Female", "locale": "en-us", "engine": "kokoro"},
    {"id": "am_adam",  "name": "Adam (AM)",                   "gender": "Male",   "locale": "en-us", "engine": "kokoro"},
    {"id": "am_echo",  "name": "Echo (AM)",                   "gender": "Male",   "locale": "en-us", "engine": "kokoro"},
    {"id": "am_eric",  "name": "Eric (AM)",                   "gender": "Male",   "locale": "en-us", "engine": "kokoro"},
    {"id": "am_fenrir","name": "Fenrir (AM)",                  "gender": "Male",   "locale": "en-us", "engine": "kokoro"},
    {"id": "am_liam",  "name": "Liam (AM)",                   "gender": "Male",   "locale": "en-us", "engine": "kokoro"},
    {"id": "am_michael","name": "Michael (AM)",               "gender": "Male",   "locale": "en-us", "engine": "kokoro"},
    {"id": "am_onyx",  "name": "Onyx (AM)",                   "gender": "Male",   "locale": "en-us", "engine": "kokoro"},
    {"id": "bf_emma",  "name": "Emma (BF — British Female)",  "gender": "Female", "locale": "en-gb", "engine": "kokoro"},
    {"id": "bf_isabella","name": "Isabella (BF)",             "gender": "Female", "locale": "en-gb", "engine": "kokoro"},
    {"id": "bm_george","name": "George (BM — British Male)",  "gender": "Male",   "locale": "en-gb", "engine": "kokoro"},
    {"id": "bm_lewis", "name": "Lewis (BM)",                  "gender": "Male",   "locale": "en-gb", "engine": "kokoro"},
]

_KOKORO_MODEL_FILENAMES = ["kokoro-v1.0-q8.onnx", "kokoro-v1.0.onnx"]
_KOKORO_VOICES_FILENAME = "voices-v1.0.bin"


def _find_kokoro_model() -> tuple[str, str] | None:
    """Search common locations for Kokoro model files.

    Returns *(model_path, voices_path)* or None if not found.
    """
    search_dirs = [
        Path.home() / ".cache" / "kokoro",
        Path.home() / "kokoro",
        Path("/usr/local/share/kokoro"),
        Path("/opt/kokoro"),
        Path.cwd(),
        Path.cwd() / "models",
    ]

    for directory in search_dirs:
        if not directory.exists():
            continue
        voices_path = directory / _KOKORO_VOICES_FILENAME
        if not voices_path.exists():
            continue
        for model_name in _KOKORO_MODEL_FILENAMES:
            model_path = directory / model_name
            if model_path.exists():
                return str(model_path), str(voices_path)

    return None


class KokoroEngine(TTSEngine):
    """Kokoro ONNX offline TTS engine.

    The model is loaded lazily on the first call to :meth:`generate`.
    Supports the q8 quantised model (``kokoro-v1.0-q8.onnx``) if found,
    falling back to the full-precision model.
    """

    def __init__(self) -> None:
        self._model: Any = None          # kokoro_onnx.Kokoro instance
        self._model_path: str | None = None
        self._lock = asyncio.Lock()

    @property
    def max_concurrent(self) -> int:
        return 1

    @property
    def requires_internet(self) -> bool:
        return False

    @property
    def engine_id(self) -> str:
        return "kokoro"

    # ------------------------------------------------------------------
    # Lazy model loading
    # ------------------------------------------------------------------

    async def _ensure_model(self) -> None:
        if self._model is not None:
            return

        async with self._lock:
            if self._model is not None:
                return  # another coroutine loaded it while we waited

            paths = _find_kokoro_model()
            if paths is None:
                raise FileNotFoundError(
                    "Kokoro model files not found. "
                    "Please download 'kokoro-v1.0.onnx' (or 'kokoro-v1.0-q8.onnx') "
                    "and 'voices-v1.0.bin' and place them in ~/.cache/kokoro/ "
                    "or the current working directory. "
                    "See https://github.com/thewh1teagle/kokoro-onnx for details."
                )

            model_path, voices_path = paths
            logger.info("Loading Kokoro model from %s", model_path)

            try:
                import kokoro_onnx  # lazy import

                self._model = await asyncio.to_thread(
                    kokoro_onnx.Kokoro, model_path, voices_path
                )
                self._model_path = model_path
                logger.info("Kokoro model loaded successfully.")
            except Exception as exc:
                raise RuntimeError(f"Failed to load Kokoro model: {exc}") from exc

    # ------------------------------------------------------------------
    # Voice listing
    # ------------------------------------------------------------------

    def list_voices(self) -> list[dict]:
        return list(_KOKORO_VOICES)

    # ------------------------------------------------------------------
    # Generation
    # ------------------------------------------------------------------

    async def generate(
        self,
        text: str,
        voice: str,
        speed: float = 1.0,
        output_path: str = None,
    ) -> TTSResult:
        """Synthesise *text* offline using the Kokoro ONNX model."""
        await self._ensure_model()

        import soundfile as sf  # lazy import
        import kokoro_onnx

        if output_path is None:
            output_path = os.path.join(
                tempfile.gettempdir(), f"kokoro_{uuid.uuid4().hex}.wav"
            )

        try:
            samples, sample_rate = await asyncio.to_thread(
                self._model.create, text, voice=voice, speed=speed
            )
        except Exception as exc:
            raise RuntimeError(
                f"Kokoro synthesis failed for voice '{voice}': {exc}"
            ) from exc

        await asyncio.to_thread(sf.write, output_path, samples, sample_rate)

        duration = len(samples) / sample_rate
        return TTSResult(
            audio_path=output_path,
            duration_seconds=duration,
            sample_rate=sample_rate,
        )

    # ------------------------------------------------------------------
    # Preview
    # ------------------------------------------------------------------

    async def preview(self, voice: str, sample_text: str = None) -> TTSResult:
        text = sample_text or _PREVIEW_TEXT
        return await self.generate(text, voice=voice, speed=1.0)


# ---------------------------------------------------------------------------
# TTSEngineFactory
# ---------------------------------------------------------------------------

class TTSEngineFactory:
    """Factory that returns singleton engine instances keyed by engine_id.

    Singletons avoid re-loading heavy models (e.g. Kokoro) between calls.
    """

    _instances: dict[str, TTSEngine] = {}

    @staticmethod
    def get(engine_id: str) -> TTSEngine:
        """Return the singleton engine for the given *engine_id*.

        Supported ids: ``"edge-tts"``, ``"kokoro"``.

        Raises :class:`ValueError` for unknown engine ids.
        """
        if engine_id not in TTSEngineFactory._instances:
            if engine_id == "edge-tts":
                TTSEngineFactory._instances[engine_id] = EdgeTTSEngine()
            elif engine_id == "kokoro":
                TTSEngineFactory._instances[engine_id] = KokoroEngine()
            else:
                raise ValueError(
                    f"Unknown TTS engine: '{engine_id}'. "
                    f"Valid options: 'edge-tts', 'kokoro'."
                )
        return TTSEngineFactory._instances[engine_id]

    @staticmethod
    def reset(engine_id: str | None = None) -> None:
        """Drop singleton(s) — primarily useful in tests."""
        if engine_id is None:
            TTSEngineFactory._instances.clear()
        else:
            TTSEngineFactory._instances.pop(engine_id, None)


# ===========================================================================
# FFmpeg / ffprobe helpers
# ===========================================================================


def _run_ffmpeg(args: list[str], check: bool = True) -> subprocess.CompletedProcess:
    """Run an FFmpeg command, capturing stdout/stderr.

    Raises :class:`subprocess.CalledProcessError` (if *check*) or returns the
    completed-process object so callers can inspect stderr on failure.
    """
    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error"] + args
    return subprocess.run(cmd, capture_output=True, text=True, check=check)


def _run_ffprobe(args: list[str]) -> subprocess.CompletedProcess:
    cmd = ["ffprobe", "-hide_banner", "-loglevel", "error"] + args
    return subprocess.run(cmd, capture_output=True, text=True, check=True)


# ---------------------------------------------------------------------------
# get_duration_ffprobe
# ---------------------------------------------------------------------------

def get_duration_ffprobe(audio_path: str) -> float:
    """Return the duration of *audio_path* in seconds using ffprobe.

    Raises :class:`RuntimeError` if the file cannot be probed.
    """
    try:
        result = _run_ffprobe([
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            audio_path,
        ])
        return float(result.stdout.strip())
    except (subprocess.CalledProcessError, ValueError) as exc:
        raise RuntimeError(
            f"ffprobe failed to get duration of '{audio_path}': {exc}"
        ) from exc


# ---------------------------------------------------------------------------
# generate_silence
# ---------------------------------------------------------------------------

def generate_silence(
    duration_seconds: float,
    output_path: str,
    sample_rate: int = 24000,
) -> str:
    """Generate a silent WAV file of exactly *duration_seconds* length.

    Returns *output_path* on success.
    """
    try:
        _run_ffmpeg([
            "-f", "lavfi",
            "-i", f"anullsrc=r={sample_rate}:cl=mono",
            "-t", str(duration_seconds),
            "-ar", str(sample_rate),
            "-ac", "1",
            output_path,
        ])
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(
            f"Failed to generate silence file '{output_path}': {exc.stderr}"
        ) from exc
    return output_path


# ---------------------------------------------------------------------------
# SilenceCache
# ---------------------------------------------------------------------------

class SilenceCache:
    """Cache for commonly used silence files so they are generated only once.

    Default durations (seconds): ``2.0``, ``1.0``, ``0.5``, ``0.3``.
    Files are stored in the system temp directory and reused across the session.
    """

    _DEFAULT_DURATIONS = (2.0, 1.0, 0.5, 0.3)

    def __init__(
        self,
        cache_dir: str | None = None,
        durations: tuple[float, ...] = _DEFAULT_DURATIONS,
        sample_rate: int = 24000,
    ) -> None:
        self._cache_dir = cache_dir or tempfile.gettempdir()
        self._sample_rate = sample_rate
        self._cache: dict[float, str] = {}
        self._pre_generate(durations)

    def _pre_generate(self, durations: tuple[float, ...]) -> None:
        for dur in durations:
            self._get_or_create(dur)

    def _get_or_create(self, duration: float) -> str:
        if duration not in self._cache:
            filename = f"silence_{duration:.3f}s_{self._sample_rate}hz.wav"
            path = os.path.join(self._cache_dir, filename)
            if not os.path.exists(path):
                generate_silence(duration, path, self._sample_rate)
            self._cache[duration] = path
        return self._cache[duration]

    def get(self, duration: float) -> str:
        """Return path to a silence file of *duration* seconds (creates if needed)."""
        return self._get_or_create(duration)

    def clear(self) -> None:
        """Delete cached silence files and reset the registry."""
        for path in self._cache.values():
            try:
                os.unlink(path)
            except OSError:
                pass
        self._cache.clear()


# Module-level singleton cache — initialised lazily on first use.
_silence_cache: SilenceCache | None = None


def _get_silence_cache() -> SilenceCache:
    global _silence_cache
    if _silence_cache is None:
        _silence_cache = SilenceCache()
    return _silence_cache


# ---------------------------------------------------------------------------
# concat_audio_files
# ---------------------------------------------------------------------------

def concat_audio_files(
    file_list: list[str],
    output_path: str,
    silence_between: dict | None = None,
) -> str:
    """Concatenate audio files using the FFmpeg concat demuxer.

    Parameters
    ----------
    file_list:
        Ordered list of audio file paths to concatenate.
    output_path:
        Path for the output file.
    silence_between:
        Optional dict that maps boundary-type keys to silence durations in
        seconds.  The dict may contain any of: ``"chapter"``, ``"scene"``,
        ``"paragraph"``, ``"dialogue"``.  To use, embed marker strings of
        the form ``__SILENCE_chapter__``, ``__SILENCE_scene__``, etc. in
        *file_list* in place of real audio files — they will be replaced by
        silence segments of the corresponding duration.

        Example::

            silence_between = {"chapter": 2.0, "scene": 1.0,
                                "paragraph": 0.5, "dialogue": 0.3}

    Returns the *output_path*.
    """
    if not file_list:
        raise ValueError("file_list must not be empty")

    silence_cache = _get_silence_cache()

    resolved: list[str] = []
    for item in file_list:
        if isinstance(item, str) and item.startswith("__SILENCE_"):
            # Extract key, e.g. "__SILENCE_chapter__" → "chapter"
            key = item.strip("_").replace("SILENCE_", "")
            if silence_between and key in silence_between:
                dur = silence_between[key]
                resolved.append(silence_cache.get(dur))
            # If key not in silence_between, skip the marker silently.
        else:
            resolved.append(item)

    if not resolved:
        raise ValueError("No real audio files remain after resolving silence markers.")

    # Write FFmpeg concat list file.
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".txt", delete=False, encoding="utf-8"
    ) as fh:
        list_path = fh.name
        for audio_path in resolved:
            # FFmpeg requires single-quotes escaped inside the path value.
            safe = audio_path.replace("'", r"\'")
            fh.write(f"file '{safe}'\n")

    try:
        _run_ffmpeg([
            "-f", "concat",
            "-safe", "0",
            "-i", list_path,
            "-c", "copy",
            output_path,
        ])
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(
            f"FFmpeg concat failed: {exc.stderr}"
        ) from exc
    finally:
        os.unlink(list_path)

    return output_path


# ---------------------------------------------------------------------------
# normalize_loudness
# ---------------------------------------------------------------------------

def normalize_loudness(
    input_path: str,
    output_path: str,
    target_lufs: float = -19.0,
) -> str:
    """Two-pass EBU R128 loudness normalisation for audiobooks.

    Pass 1 measures the current integrated loudness, true peak, and LRA.
    Pass 2 applies the correction to reach *target_lufs* (default −19 LUFS,
    a good target for spoken-word audiobooks).

    Returns *output_path*.
    """
    # --- Pass 1: measure ---
    measure_result = subprocess.run(
        [
            "ffmpeg", "-hide_banner",
            "-i", input_path,
            "-af", f"loudnorm=I={target_lufs}:TP=-1.5:LRA=11:print_format=json",
            "-f", "null", "-",
        ],
        capture_output=True,
        text=True,
    )

    # loudnorm prints JSON to stderr.
    stderr = measure_result.stderr
    json_match = re.search(r"\{[^}]+\}", stderr, re.DOTALL)
    if not json_match:
        raise RuntimeError(
            f"loudnorm pass-1 did not return JSON measurements.\n"
            f"ffmpeg stderr:\n{stderr}"
        )

    try:
        stats = json.loads(json_match.group())
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Failed to parse loudnorm JSON: {exc}") from exc

    measured_i   = stats.get("input_i",    "-70.0")
    measured_tp  = stats.get("input_tp",   "-6.0")
    measured_lra = stats.get("input_lra",  "7.0")
    measured_thresh = stats.get("input_thresh", "-80.0")
    offset       = stats.get("target_offset", "0.0")

    # --- Pass 2: apply ---
    loudnorm_filter = (
        f"loudnorm=I={target_lufs}:TP=-1.5:LRA=11"
        f":measured_I={measured_i}"
        f":measured_TP={measured_tp}"
        f":measured_LRA={measured_lra}"
        f":measured_thresh={measured_thresh}"
        f":offset={offset}"
        f":linear=true:print_format=none"
    )

    try:
        _run_ffmpeg([
            "-i", input_path,
            "-af", loudnorm_filter,
            output_path,
        ])
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(
            f"loudnorm pass-2 failed: {exc.stderr}"
        ) from exc

    return output_path


# ---------------------------------------------------------------------------
# mix_with_background_music
# ---------------------------------------------------------------------------

def mix_with_background_music(
    narration_path: str,
    music_path: str,
    output_path: str,
    music_volume_db: float = -15.0,
) -> str:
    """Mix narration with looped background music.

    The music is ducked to *music_volume_db* dB relative to its original level.
    The music is looped to match the narration length if necessary, and fades
    out during the final 3 seconds.

    Returns *output_path*.
    """
    narration_dur = get_duration_ffprobe(narration_path)
    fade_start = max(0.0, narration_dur - 3.0)

    # afade: fade-out the music in the last 3 seconds.
    music_filter = (
        f"volume={music_volume_db}dB,"
        f"afade=t=out:st={fade_start:.3f}:d=3"
    )

    filter_complex = (
        f"[1:a]{music_filter}[music_adj];"
        "[0:a][music_adj]amix=inputs=2:duration=first:dropout_transition=3[out]"
    )

    try:
        _run_ffmpeg([
            "-i", narration_path,
            "-stream_loop", "-1",   # loop music indefinitely
            "-i", music_path,
            "-filter_complex", filter_complex,
            "-map", "[out]",
            "-t", str(narration_dur),  # truncate to narration length
            output_path,
        ])
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(
            f"Background music mix failed: {exc.stderr}"
        ) from exc

    return output_path


# ---------------------------------------------------------------------------
# generate_chapter_metadata_file
# ---------------------------------------------------------------------------

def generate_chapter_metadata_file(manifest: dict, output_path: str) -> str:
    """Write an FFmpeg metadata file that encodes M4B chapter markers.

    *manifest* must contain at least::

        {
            "title":   "Book Title",
            "author":  "Author Name",
            "chapters": [
                {"title": "Chapter 1", "start_ms": 0,     "end_ms": 120000},
                {"title": "Chapter 2", "start_ms": 120000, "end_ms": 240000},
                ...
            ]
        }

    Returns *output_path*.
    """
    lines: list[str] = [
        ";FFMETADATA1",
        f"title={manifest.get('title', 'Untitled')}",
        f"artist={manifest.get('author', 'Unknown')}",
        f"album={manifest.get('title', 'Untitled')}",
        f"genre={manifest.get('genre', 'Audiobook')}",
        f"date={manifest.get('year', '')}",
        f"comment={manifest.get('description', '')}",
        "",
    ]

    for chapter in manifest.get("chapters", []):
        start_ms = int(chapter.get("start_ms", 0))
        end_ms   = int(chapter.get("end_ms", start_ms))
        title    = chapter.get("title", "Chapter")
        lines += [
            "[CHAPTER]",
            "TIMEBASE=1/1000",
            f"START={start_ms}",
            f"END={end_ms}",
            f"title={title}",
            "",
        ]

    with open(output_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))

    return output_path


# ---------------------------------------------------------------------------
# encode_to_m4b
# ---------------------------------------------------------------------------

def encode_to_m4b(
    mp3_path: str,
    metadata: dict,
    chapters_meta_path: str,
    cover_art_path: str = None,
    output_path: str = None,
) -> str:
    """Encode an audio file to M4B with embedded chapter markers and cover art.

    Parameters
    ----------
    mp3_path:
        Source audio file (any format FFmpeg can decode).
    metadata:
        Dict with keys ``title``, ``author``, ``year``, ``genre``,
        ``description`` (all optional).
    chapters_meta_path:
        Path to an FFmpeg metadata file generated by
        :func:`generate_chapter_metadata_file`.
    cover_art_path:
        Optional path to a JPEG/PNG image to embed as cover art.
    output_path:
        Destination M4B path.  Defaults to *mp3_path* with ``.m4b`` extension.

    Returns the *output_path*.
    """
    if output_path is None:
        output_path = str(Path(mp3_path).with_suffix(".m4b"))

    cmd: list[str] = [
        "-i", mp3_path,
        "-i", chapters_meta_path,
    ]

    if cover_art_path:
        cmd += ["-i", cover_art_path]

    # Map streams.
    cmd += ["-map_metadata", "1", "-map_chapters", "1"]
    cmd += ["-map", "0:a"]
    if cover_art_path:
        cmd += [
            "-map", "2:v",
            "-disposition:v:0", "attached_pic",
            "-c:v", "copy",
        ]

    # Audio codec + metadata tags.
    cmd += [
        "-c:a", "aac",
        "-b:a", "64k",
        "-ac", "1",
        "-metadata", f"title={metadata.get('title', 'Untitled')}",
        "-metadata", f"artist={metadata.get('author', 'Unknown')}",
        "-metadata", f"album={metadata.get('title', 'Untitled')}",
        "-metadata", f"date={metadata.get('year', '')}",
        "-metadata", f"genre={metadata.get('genre', 'Audiobook')}",
        "-metadata", f"comment={metadata.get('description', '')}",
        output_path,
    ]

    try:
        _run_ffmpeg(cmd)
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(
            f"M4B encoding failed: {exc.stderr}"
        ) from exc

    return output_path


# ===========================================================================
# Improvements / extras
# ===========================================================================


# ---------------------------------------------------------------------------
# adjust_speed_atempo
# ---------------------------------------------------------------------------

def adjust_speed_atempo(
    input_path: str,
    output_path: str,
    speed: float,
) -> str:
    """Change playback speed of *input_path* using the ``atempo`` filter.

    ``atempo`` is limited to the range [0.5, 2.0].  For speeds outside that
    range the filter is chained (e.g. speed=4.0 → ``atempo=2.0,atempo=2.0``).

    Parameters
    ----------
    speed:
        Target speed multiplier (e.g. ``1.5`` = 50 % faster).

    Returns *output_path*.
    """
    if speed <= 0:
        raise ValueError(f"speed must be positive, got {speed}")

    if abs(speed - 1.0) < 1e-4:
        # Nothing to do — copy.
        try:
            _run_ffmpeg(["-i", input_path, "-c", "copy", output_path])
        except subprocess.CalledProcessError as exc:
            raise RuntimeError(f"atempo copy failed: {exc.stderr}") from exc
        return output_path

    # Build a chain of atempo filters, each in [0.5, 2.0].
    filters: list[str] = []
    remaining = speed

    if speed > 1.0:
        while remaining > 2.0 + 1e-9:
            filters.append("atempo=2.0")
            remaining /= 2.0
        filters.append(f"atempo={remaining:.6f}")
    else:
        while remaining < 0.5 - 1e-9:
            filters.append("atempo=0.5")
            remaining /= 0.5
        filters.append(f"atempo={remaining:.6f}")

    af = ",".join(filters)

    try:
        _run_ffmpeg(["-i", input_path, "-af", af, output_path])
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(
            f"atempo speed adjustment failed: {exc.stderr}"
        ) from exc

    return output_path


# ---------------------------------------------------------------------------
# detect_audio_issues
# ---------------------------------------------------------------------------

def detect_audio_issues(audio_path: str) -> dict:
    """Analyse *audio_path* for common audio quality issues.

    Runs a single FFmpeg ``loudnorm`` measurement pass and inspects the
    ``volumedetect`` filter output to derive:

    - ``clipping``          : True if true-peak ≥ 0 dBTP
    - ``silence_percentage``: estimated percentage of the file that is silent
    - ``peak_db``           : maximum sample peak in dB
    - ``lufs``              : integrated loudness in LUFS

    Returns a plain dict so callers can log, display, or act on the findings.
    """
    result: dict = {
        "clipping":           False,
        "silence_percentage": 0.0,
        "peak_db":            -120.0,
        "lufs":               -70.0,
    }

    # --- loudnorm measurement ---
    lnorm_proc = subprocess.run(
        [
            "ffmpeg", "-hide_banner",
            "-i", audio_path,
            "-af", "loudnorm=I=-19:TP=-1.5:LRA=11:print_format=json",
            "-f", "null", "-",
        ],
        capture_output=True,
        text=True,
    )
    json_match = re.search(r"\{[^}]+\}", lnorm_proc.stderr, re.DOTALL)
    if json_match:
        try:
            stats = json.loads(json_match.group())
            result["lufs"]     = float(stats.get("input_i",  -70.0))
            input_tp           = float(stats.get("input_tp", -120.0))
            result["clipping"] = input_tp >= 0.0
        except (ValueError, json.JSONDecodeError):
            pass

    # --- volumedetect for peak and silence estimation ---
    vol_proc = subprocess.run(
        [
            "ffmpeg", "-hide_banner",
            "-i", audio_path,
            "-af", "volumedetect",
            "-f", "null", "-",
        ],
        capture_output=True,
        text=True,
    )
    stderr = vol_proc.stderr

    max_vol_match = re.search(r"max_volume:\s*([-\d.]+)\s*dB", stderr)
    if max_vol_match:
        result["peak_db"] = float(max_vol_match.group(1))

    # Estimate silence: compare mean volume to a −50 dB threshold.
    mean_vol_match = re.search(r"mean_volume:\s*([-\d.]+)\s*dB", stderr)
    if mean_vol_match:
        mean_db = float(mean_vol_match.group(1))
        # Treat the segment as "mostly silent" if mean is below −50 dB.
        if mean_db < -50.0:
            result["silence_percentage"] = 100.0
        elif mean_db < -40.0:
            # Linear interpolation between −50 dB (100 % silent) and −40 dB (0 %).
            result["silence_percentage"] = ((-40.0 - mean_db) / 10.0) * 100.0

    return result


# ---------------------------------------------------------------------------
# generate_batch
# ---------------------------------------------------------------------------

async def generate_batch(
    engine: TTSEngine,
    segments: list[dict],
    cancel_event: asyncio.Event,
    progress_cb: Callable[[int, int, TTSResult | Exception], None] | None = None,
) -> list[TTSResult | Exception]:
    """Generate TTS audio for multiple segments concurrently.

    Each element of *segments* is a dict with at minimum:
    - ``text``  (str): the text to synthesise
    - ``voice`` (str): voice id understood by *engine*
    - ``speed`` (float, optional): playback speed multiplier, default 1.0
    - ``output_path`` (str, optional): destination file path

    Concurrency is bounded by ``engine.max_concurrent``.

    *cancel_event*: set this to request graceful cancellation; in-flight tasks
    will be awaited to completion but no new tasks will be started.

    *progress_cb*: called after each segment completes (or fails), with
    arguments ``(index, total, result_or_exception)``.

    Returns a list with one :class:`TTSResult` (or :class:`Exception`) per
    input segment, preserving order.
    """
    total = len(segments)
    results: list[TTSResult | Exception | None] = [None] * total
    semaphore = asyncio.Semaphore(engine.max_concurrent)

    async def _worker(idx: int, seg: dict) -> None:
        if cancel_event.is_set():
            results[idx] = asyncio.CancelledError("Batch generation cancelled.")
            if progress_cb:
                progress_cb(idx, total, results[idx])
            return

        async with semaphore:
            if cancel_event.is_set():
                results[idx] = asyncio.CancelledError("Batch generation cancelled.")
                if progress_cb:
                    progress_cb(idx, total, results[idx])
                return

            try:
                tts_result = await engine.generate(
                    text=seg["text"],
                    voice=seg["voice"],
                    speed=seg.get("speed", 1.0),
                    output_path=seg.get("output_path"),
                )
                results[idx] = tts_result
            except Exception as exc:
                logger.warning("generate_batch: segment %d failed: %s", idx, exc)
                results[idx] = exc

            if progress_cb:
                progress_cb(idx, total, results[idx])

    tasks = [asyncio.create_task(_worker(i, seg)) for i, seg in enumerate(segments)]
    await asyncio.gather(*tasks, return_exceptions=True)

    return results  # type: ignore[return-value]
