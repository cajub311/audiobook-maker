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
import json
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
import wave
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Optional
from urllib.parse import urlparse
from urllib.request import Request, urlopen


APP_VERSION = "7.0"
BASE_DIR = Path(__file__).resolve().parent
CACHE_DIR = BASE_DIR / "tts_cache"
MANIFESTS_DIR = BASE_DIR / "manifests"
PRONUNCIATIONS_DIR = BASE_DIR / "pronunciations"
TEMP_DIR = BASE_DIR / "temp"
OUTPUT_DIR = BASE_DIR / "output"


def ensure_runtime_dirs() -> None:
    for directory in (CACHE_DIR, MANIFESTS_DIR, PRONUNCIATIONS_DIR, TEMP_DIR, OUTPUT_DIR):
        directory.mkdir(parents=True, exist_ok=True)


def slugify(value: str, fallback: str = "book") -> str:
    clean = re.sub(r"[^A-Za-z0-9._-]+", "_", (value or "").strip())
    clean = clean.strip("._")
    return clean or fallback


def now_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat()


def run_command(command: list[str], check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, check=check, capture_output=True, text=True)


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


def atomic_json_write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", delete=False, dir=str(path.parent), encoding="utf-8") as tmp:
        json.dump(payload, tmp, indent=2, ensure_ascii=False)
        tmp.flush()
        os.fsync(tmp.fileno())
        temp_name = tmp.name
    os.replace(temp_name, path)


def save_manifest(manifest: dict[str, Any], manifest_path: str | Path) -> None:
    atomic_json_write(Path(manifest_path), manifest)


def load_manifest(manifest_path: str | Path) -> dict[str, Any]:
    with open(manifest_path, "r", encoding="utf-8") as f:
        return json.load(f)


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
        sample = "This is a short preview of the selected narration voice."
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
        sample = "This is a short preview generated by Kokoro."
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
        self.index = self._load_index()

    def _load_index(self) -> dict[str, dict[str, Any]]:
        if not self.index_path.exists():
            return {}
        try:
            with open(self.index_path, "r", encoding="utf-8") as f:
                payload = json.load(f)
            return payload if isinstance(payload, dict) else {}
        except Exception:
            return {}

    def _save_index(self) -> None:
        atomic_json_write(self.index_path, self.index)

    def _make_key(self, text: str, voice: str, engine: str, speed: float) -> str:
        return hashlib.md5(f"{text}|{voice}|{engine}|{speed}".encode("utf-8")).hexdigest()

    def get(self, text: str, voice: str, engine: str, speed: float = 1.0) -> Optional[str]:
        key = self._make_key(text, voice, engine, speed)
        entry = self.index.get(key)
        if not entry:
            return None
        path = self.cache_dir / entry.get("filename", "")
        if not path.exists():
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
    ) -> str:
        key = self._make_key(text, voice, engine, speed)
        ext = Path(audio_path).suffix or ".mp3"
        cache_filename = f"{key}{ext}"
        cache_path = self.cache_dir / cache_filename
        if Path(audio_path).resolve() != cache_path.resolve():
            shutil.copy2(audio_path, cache_path)
        size = cache_path.stat().st_size if cache_path.exists() else 0
        self.index[key] = {
            "filename": cache_filename,
            "voice": voice,
            "engine": engine,
            "duration": float(duration),
            "size_bytes": size,
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
    try:
        import trafilatura  # type: ignore

        downloaded = trafilatura.fetch_url(url)
        if not downloaded:
            return ""
        extracted = trafilatura.extract(downloaded, include_comments=False, include_tables=False)
        return extracted or ""
    except Exception:
        req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urlopen(req, timeout=20) as response:
            html = response.read().decode("utf-8", errors="ignore")
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
    settings.setdefault("character_voices", {})
    settings.setdefault("pronunciation_overrides", {})
    settings.setdefault("background_music", None)
    settings.setdefault("music_duck_db", -15)
    settings.setdefault("output_format", "m4b")

    source_chapters, meta, source_ref, source_type = extract_source_chapters(input_path, url, raw_text)
    cache = AudioCache()

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
                cached_file = cache.get(chunk, voice, engine_name, speed=speed)
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
    manifest["progress"]["estimated_remaining_seconds"] = estimate_generation_seconds(total_chars, engine_name)
    manifest["character_occurrences"] = character_occurrences

    manifest_name = f"{slugify(book_title)}_manifest.json"
    manifest_path = str(MANIFESTS_DIR / manifest_name)
    save_manifest(manifest, manifest_path)
    return manifest, manifest_path


async def stage_generate(
    manifest: dict[str, Any],
    manifest_path: Optional[str] = None,
    cancel_event: Optional[threading.Event] = None,
    progress_callback: Optional[Callable[[int, int, str], None]] = None,
) -> dict[str, Any]:
    ensure_runtime_dirs()
    settings = manifest.get("settings", {})
    engine_name = settings.get("tts_engine", "edge-tts")
    engine = create_tts_engine(engine_name)
    cache = AudioCache()
    pronunciation = PronunciationDict(settings.get("pronunciation_overrides", {}))
    speed = float(settings.get("speed_multiplier", 1.0))

    pending: list[tuple[int, int]] = []
    for c_idx, chapter in enumerate(manifest.get("chapters", [])):
        for s_idx, segment in enumerate(chapter.get("segments", [])):
            if segment.get("status") != "cached":
                pending.append((c_idx, s_idx))

    total = len(pending)
    done = 0
    manifest["progress"]["generation_started"] = manifest["progress"].get("generation_started") or now_iso()

    if total == 0:
        if progress_callback:
            progress_callback(1, 1, "All segments already cached.")
        return manifest

    sem = asyncio.Semaphore(max(1, int(settings.get("max_concurrent", engine.max_concurrent))))
    lock = asyncio.Lock()

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
        try:
            cached = cache.get(transformed_text, voice, engine_name, speed=speed)
            if cached:
                duration = get_duration_ffprobe(cached)
                async with lock:
                    segment["cache_file"] = cached
                    segment["duration_seconds"] = duration
                    segment["status"] = "cached"
            else:
                ext = ".mp3" if "edge" in engine_name.lower() else ".wav"
                tmp_path = str(CACHE_DIR / f"{segment['text_hash']}_{slugify(voice)}{ext}")
                async with sem:
                    if cancel_event and cancel_event.is_set():
                        return
                    result = await engine.generate(
                        text=transformed_text,
                        voice=voice,
                        speed=speed,
                        output_path=tmp_path,
                    )
                cache_path = cache.put(
                    transformed_text,
                    voice,
                    engine_name,
                    speed=speed,
                    audio_path=result.audio_path,
                    duration=result.duration_seconds,
                )
                duration = result.duration_seconds or get_duration_ffprobe(cache_path)
                async with lock:
                    segment["cache_file"] = cache_path
                    segment["duration_seconds"] = duration
                    segment["status"] = "cached"

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

    tasks = [asyncio.create_task(process_one(ch, seg)) for ch, seg in pending]
    await asyncio.gather(*tasks)
    manifest["progress"]["completed_segments"] = sum(
        1 for chapter in manifest["chapters"] for seg in chapter["segments"] if seg.get("status") == "cached"
    )
    if manifest_path:
        save_manifest(manifest, manifest_path)
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
    pass1 = subprocess.run(cmd1, capture_output=True, text=True, check=False)
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
    run_command(cmd2)
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
    run_command(cmd)
    return output_path


def stage_assemble(
    manifest: dict[str, Any],
    output_format: str = "m4b",
    normalize_audio: bool = True,
) -> str:
    ensure_runtime_dirs()
    if not ffmpeg_exists():
        raise RuntimeError("FFmpeg and ffprobe are required for assembly stage.")

    chapter_gap = create_silence_file(2.0, TEMP_DIR / "silence_2s.mp3")
    scene_gap = create_silence_file(1.0, TEMP_DIR / "silence_1s.mp3")
    para_gap = create_silence_file(0.5, TEMP_DIR / "silence_05s.mp3")
    dialogue_gap = create_silence_file(0.3, TEMP_DIR / "silence_03s.mp3")

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
    run_command(
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

    assembled_path = concatenated

    settings = manifest.get("settings", {})
    bg_music = settings.get("background_music")
    if bg_music:
        mixed = TEMP_DIR / "mixed.mp3"
        duck_db = settings.get("music_duck_db", -15)
        run_command(
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
        assembled_path = mixed

    if normalize_audio:
        normalized = TEMP_DIR / "normalized.mp3"
        assembled_path = Path(normalize_loudness(str(assembled_path), str(normalized)))

    book_title = slugify(manifest.get("book", {}).get("title", "Audiobook"), fallback="audiobook")
    if output_format.lower() == "m4b":
        metadata_file = TEMP_DIR / "chapters_meta.txt"
        generate_chapter_metadata(manifest, str(metadata_file))
        output_path = OUTPUT_DIR / f"{book_title}.m4b"
        run_command(
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


def voices_for_engine(engine_label: str) -> list[str]:
    engine = create_tts_engine(normalize_engine_label(engine_label))
    voices = [v.get("name", "") for v in engine.list_voices()]
    return [v for v in voices if v]


def build_ui():
    try:
        import gradio as gr  # type: ignore
    except Exception as exc:
        raise RuntimeError(f"Gradio is required for UI mode: {exc}") from exc

    ensure_runtime_dirs()
    cancel_event = threading.Event()

    with gr.Blocks(title="Audiobook Creator V7", theme=gr.themes.Soft()) as app:
        manifest_path_state = gr.State("")

        with gr.Tab("Input"):
            with gr.Row():
                file_input = gr.File(label="Book file (EPUB/PDF/TXT)", file_types=[".epub", ".pdf", ".txt"], scale=2)
                url_input = gr.Textbox(label="URL", placeholder="https://...", scale=1)
            text_input = gr.Textbox(label="Or paste raw text", lines=8)
            parse_btn = gr.Button("Parse & Build Manifest", variant="primary")
            parse_status = gr.Markdown("")
            chapter_list = gr.Dataframe(
                headers=["Chapter", "Segments", "Characters Found", "Cache Status"],
                value=[],
                interactive=False,
            )
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
            character_table = gr.Dataframe(
                headers=["Character", "Voice", "Detection Method", "Occurrences"],
                value=[],
                interactive=True,
            )
            pronunciation_table = gr.Dataframe(headers=["Word", "Sounds Like"], value=[], interactive=True)
            speed_slider = gr.Slider(0.8, 1.3, value=1.0, step=0.05, label="Speed")
            with gr.Accordion("Background music", open=False):
                music_file = gr.File(label="Music MP3", file_types=[".mp3"])
                music_volume = gr.Slider(-25, -5, value=-15, step=1, label="Music duck volume (dB)")

        with gr.Tab("Generate"):
            with gr.Row():
                generate_btn = gr.Button("Generate Audiobook", variant="primary", scale=2)
                cancel_btn = gr.Button("Cancel", variant="stop", scale=1)
            output_format = gr.Radio(["M4B (Chaptered)", "MP3"], value="M4B (Chaptered)", label="Output Format")
            normalize_check = gr.Checkbox(label="Normalize loudness (-19 LUFS)", value=True)
            progress_text = gr.Markdown("")
            chapter_progress = gr.Dataframe(headers=["Chapter", "Status", "Segments Done"], value=[])

        with gr.Tab("Player"):
            audio_player = gr.Audio(label="Audiobook", type="filepath")
            chapter_nav = gr.Dropdown(label="Jump to Chapter", choices=[])
            download_file = gr.File(label="Download")

        def on_engine_change(engine_label: str):
            voice_choices = voices_for_engine(engine_label)
            default_n = voice_choices[0] if voice_choices else None
            default_d = voice_choices[1] if len(voice_choices) > 1 else default_n
            return (
                gr.Dropdown(choices=voice_choices, value=default_n),
                gr.Dropdown(choices=voice_choices, value=default_d),
            )

        def on_preview(engine_label: str, voice: str):
            if not voice:
                return None
            engine = create_tts_engine(normalize_engine_label(engine_label))
            result = engine.preview(voice)
            return result.audio_path

        def on_parse(
            file_obj: Any,
            url: str,
            text: str,
            engine_label: str,
            narrator: str,
            dialogue: str,
            speed: float,
            pron_rows: Any,
        ):
            try:
                input_path = getattr(file_obj, "name", None) if file_obj else None
                engine_name = normalize_engine_label(engine_label)
                narrator = narrator or "en-US-GuyNeural"
                dialogue = dialogue or "en-US-JennyNeural"
                settings = {
                    "tts_engine": engine_name,
                    "narrator_voice": narrator,
                    "dialogue_voice": dialogue,
                    "character_voices": {},
                    "pronunciation_overrides": parse_pronunciation_table(pron_rows),
                    "speed_multiplier": float(speed),
                    "background_music": None,
                    "music_duck_db": -15,
                    "output_format": "m4b",
                }
                manifest, manifest_path = stage_parse(
                    input_path=input_path,
                    settings=settings,
                    url=url,
                    raw_text=text,
                )
                chapter_rows = build_chapter_table(manifest)
                char_rows = build_character_table(manifest)
                estimate = int(manifest["progress"].get("estimated_remaining_seconds", 0))
                chapter_choices = [c.get("title", f"Chapter {i+1}") for i, c in enumerate(manifest.get("chapters", []))]
                status = (
                    f"Parsed **{len(manifest.get('chapters', []))}** chapters, "
                    f"**{manifest['progress']['total_segments']}** segments. "
                    f"Estimated generation: **~{estimate // 60} min**."
                )
                return (
                    status,
                    chapter_rows,
                    char_rows,
                    f"Estimated generation time: **~{estimate // 60} min {estimate % 60}s**",
                    manifest_path,
                    gr.Dropdown(choices=chapter_choices, value=chapter_choices[0] if chapter_choices else None),
                )
            except Exception as exc:
                return (f"Parse failed: {exc}", [], [], "", "", gr.Dropdown(choices=[], value=None))

        def on_cancel():
            cancel_event.set()
            return "Cancellation requested. Current segment(s) will finish then stop."

        def on_generate(
            manifest_path: str,
            engine_label: str,
            narrator: str,
            dialogue: str,
            speed: float,
            char_rows: Any,
            pron_rows: Any,
            out_fmt: str,
            do_normalize: bool,
            music_obj: Any,
            music_db: float,
            progress=gr.Progress(),
        ):
            if not manifest_path:
                return ("Parse a book first.", [], None, None)
            cancel_event.clear()
            try:
                manifest = load_manifest(manifest_path)
                settings = manifest.get("settings", {})
                settings["tts_engine"] = normalize_engine_label(engine_label)
                settings["narrator_voice"] = narrator or settings.get("narrator_voice", "en-US-GuyNeural")
                settings["dialogue_voice"] = dialogue or settings.get("dialogue_voice", "en-US-JennyNeural")
                settings["speed_multiplier"] = float(speed)
                settings["pronunciation_overrides"] = parse_pronunciation_table(pron_rows)
                settings["music_duck_db"] = float(music_db)
                settings["background_music"] = getattr(music_obj, "name", None) if music_obj else None
                settings["output_format"] = "m4b" if out_fmt.lower().startswith("m4b") else "mp3"

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
                    for chapter in manifest.get("chapters", []):
                        for segment in chapter.get("segments", []):
                            speaker = segment.get("speaker")
                            if speaker in updated_char_map:
                                segment["voice"] = updated_char_map[speaker]["voice"]
                                segment["status"] = "pending"
                                segment["cache_file"] = None
                                segment["duration_seconds"] = None

                manifest["settings"] = settings
                save_manifest(manifest, manifest_path)

                def progress_cb(done: int, total: int, desc: str) -> None:
                    ratio = done / total if total else 1.0
                    progress(ratio, desc=desc)

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
                    return ("Generation cancelled.", progress_rows, None, None)

                progress(0.92, desc="Assembling final audiobook")
                output_path = stage_assemble(
                    manifest=manifest,
                    output_format=settings["output_format"],
                    normalize_audio=bool(do_normalize),
                )
                progress(1.0, desc="Done")
                save_manifest(manifest, manifest_path)
                progress_rows = build_chapter_progress(manifest)
                return ("Generation complete.", progress_rows, output_path, output_path)
            except Exception as exc:
                return (f"Generation failed: {exc}", [], None, None)

        engine_select.change(
            on_engine_change,
            inputs=[engine_select],
            outputs=[narrator_voice, dialogue_voice],
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
        parse_btn.click(
            on_parse,
            inputs=[
                file_input,
                url_input,
                text_input,
                engine_select,
                narrator_voice,
                dialogue_voice,
                speed_slider,
                pronunciation_table,
            ],
            outputs=[parse_status, chapter_list, character_table, time_estimate, manifest_path_state, chapter_nav],
        )
        cancel_btn.click(on_cancel, outputs=[progress_text])
        generate_btn.click(
            on_generate,
            inputs=[
                manifest_path_state,
                engine_select,
                narrator_voice,
                dialogue_voice,
                speed_slider,
                character_table,
                pronunciation_table,
                output_format,
                normalize_check,
                music_file,
                music_volume,
            ],
            outputs=[progress_text, chapter_progress, audio_player, download_file],
        )

    return app


def main() -> None:
    ensure_runtime_dirs()
    app = build_ui()
    app.launch(server_name="0.0.0.0", server_port=7860, show_api=False)


if __name__ == "__main__":
    main()
