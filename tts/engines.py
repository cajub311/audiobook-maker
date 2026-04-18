from __future__ import annotations

import contextlib
import os
import re
import time
import wave
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional


def _parse_voice_string(voice: str) -> tuple[str, str, str | None]:
    """Parse 'VoiceName|pitch=+2Hz|rate=-5%' into (voice_name, pitch, rate_override).

    Lets callers embed pitch/rate into the voice field without changing the engine API.
    """
    parts = voice.split("|")
    voice_name = parts[0]
    pitch = "+0Hz"
    rate_override: str | None = None
    for part in parts[1:]:
        if part.startswith("pitch="):
            pitch = part[6:]
        elif part.startswith("rate="):
            rate_override = part[5:]
    return voice_name, pitch, rate_override


def _clean_for_tts(text: str) -> str:
    """Strip markup that edge-tts would read aloud as literal words."""
    text = re.sub(r"<[^>]+>", "", text)   # HTML / SSML / XML tags
    text = re.sub(r"[*_`~#\\]", "", text) # markdown emphasis / heading / escape chars
    text = re.sub(r"\s+", " ", text).strip()
    return text


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
    def __init__(self, deps: EngineDeps) -> None:
        self._deps = deps

    @property
    def max_concurrent(self) -> int:
        return 12

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
                {"name": "en-GB-ThomasMultilingualNeural", "locale": "en-GB"},
                {"name": "en-US-AvaMultilingualNeural", "locale": "en-US"},
                {"name": "en-US-AndrewMultilingualNeural", "locale": "en-US"},
                {"name": "en-GB-SoniaNeural", "locale": "en-GB"},
                {"name": "en-GB-RyanNeural", "locale": "en-GB"},
            ]

    async def generate(
        self,
        text: str,
        voice: str,
        speed: float = 1.0,
        output_path: Optional[str] = None,
    ) -> TTSResult:
        output_path = output_path or str(self._deps.temp_dir / f"edge_{int(time.time()*1000)}.mp3")
        voice_name, pitch, rate_override = _parse_voice_string(voice)
        rate_str = rate_override if rate_override else f"{int((speed - 1.0) * 100):+d}%"
        cleaned = _clean_for_tts(text)
        if not cleaned:
            cleaned = "..."
        try:
            import edge_tts  # type: ignore

            communicate = edge_tts.Communicate(text=cleaned, voice=voice_name, rate=rate_str, pitch=pitch)
            await communicate.save(output_path)
            duration = self._deps.get_duration_ffprobe_fn(output_path)
            return TTSResult(audio_path=output_path, duration_seconds=duration, sample_rate=24000)
        except Exception as exc:
            raise RuntimeError(f"edge-tts generation failed: {exc}") from exc

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

            voice_name, _, _ = _parse_voice_string(voice)
            samples, sample_rate = self._model.create(text, voice=voice_name, speed=speed)
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
