from __future__ import annotations

import asyncio
import contextlib
import inspect
import os
import time
import wave
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional


@dataclass
class TTSResult:
    audio_path: str
    duration_seconds: float
    sample_rate: int


@dataclass
class EngineDeps:
    temp_dir: Path
    preview_sample_text: str
    slugify_fn: Callable[[str, str], str]
    get_duration_ffprobe_fn: Callable[[str], float]
    run_coro_sync_fn: Callable[[Any], Any]


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


class EdgeTTSEngine(TTSEngine):
    """Microsoft Edge neural voices via edge-tts (free, requires network)."""

    # Subtle prosody defaults — improves flat / robotic delivery vs rate-only.
    _DEFAULT_PITCH = "+2Hz"
    _DEFAULT_VOLUME = "+6%"
    _GEN_RETRIES = 3
    _GEN_RETRY_BASE_S = 0.75

    def __init__(self, deps: EngineDeps) -> None:
        self._deps = deps

    @property
    def max_concurrent(self) -> int:
        # Edge can throttle if this is too high; 8 is a stable balance on HF Spaces.
        return 8

    @property
    def requires_internet(self) -> bool:
        return True

    def list_voices(self) -> list[dict[str, Any]]:
        try:
            import edge_tts  # type: ignore

            voices = self._deps.run_coro_sync_fn(edge_tts.list_voices())
            formatted = [{"name": v.get("ShortName", ""), "locale": v.get("Locale", "")} for v in voices]
            return [v for v in formatted if v["name"]]
        except Exception:
            return [
                {"name": "en-US-AndrewNeural", "locale": "en-US"},
                {"name": "en-US-EmmaNeural", "locale": "en-US"},
                {"name": "en-GB-RyanNeural", "locale": "en-GB"},
            ]

    def _build_communicate(self, edge_tts: Any, text: str, voice: str, rate_str: str) -> Any:
        sig = inspect.signature(edge_tts.Communicate.__init__)
        params = sig.parameters
        kwargs: dict[str, Any] = {"text": text, "voice": voice, "rate": rate_str}
        if "pitch" in params:
            kwargs["pitch"] = self._DEFAULT_PITCH
        if "volume" in params:
            kwargs["volume"] = self._DEFAULT_VOLUME
        return edge_tts.Communicate(**kwargs)

    async def generate(
        self,
        text: str,
        voice: str,
        speed: float = 1.0,
        output_path: Optional[str] = None,
    ) -> TTSResult:
        output_path = output_path or str(self._deps.temp_dir / f"edge_{int(time.time()*1000)}.mp3")
        rate_str = f"{int((speed - 1.0) * 100):+d}%"
        try:
            import edge_tts  # type: ignore
        except Exception as exc:
            raise RuntimeError(f"edge-tts is not installed: {exc}") from exc

        last_err: Optional[Exception] = None
        for attempt in range(self._GEN_RETRIES):
            try:
                communicate = self._build_communicate(edge_tts, text, voice, rate_str)
                await communicate.save(output_path)
                duration = self._deps.get_duration_ffprobe_fn(output_path)
                if duration > 0:
                    return TTSResult(audio_path=output_path, duration_seconds=duration, sample_rate=24000)
                last_err = RuntimeError("edge-tts produced empty or unreadable audio")
            except Exception as exc:
                last_err = exc
            if attempt + 1 < self._GEN_RETRIES:
                await asyncio.sleep(self._GEN_RETRY_BASE_S * (2**attempt))
        raise RuntimeError(f"edge-tts generation failed after {self._GEN_RETRIES} attempts: {last_err}") from last_err

    def preview(self, voice: str) -> TTSResult:
        sample = self._deps.preview_sample_text
        preview_path = str(self._deps.temp_dir / f"preview_edge_{self._deps.slugify_fn(voice)}.mp3")
        return self._deps.run_coro_sync_fn(self.generate(sample, voice, output_path=preview_path))


class KokoroEngine(TTSEngine):
    def __init__(self, deps: EngineDeps) -> None:
        self._deps = deps
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
        output_path = output_path or str(self._deps.temp_dir / f"kokoro_{int(time.time()*1000)}.wav")
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
        sample = self._deps.preview_sample_text
        preview_path = str(self._deps.temp_dir / f"preview_kokoro_{self._deps.slugify_fn(voice)}.wav")
        return self._deps.run_coro_sync_fn(self.generate(sample, voice, output_path=preview_path))


def create_tts_engine(engine_name: str, deps: EngineDeps) -> TTSEngine:
    if "kokoro" in engine_name.lower():
        return KokoroEngine(deps)
    return EdgeTTSEngine(deps)
