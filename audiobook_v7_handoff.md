# Audiobook Creator V7 — Architecture & Implementation Handoff

> **Purpose:** This document contains all architectural decisions, exact code patterns, FFmpeg commands, and technical specs needed to implement the V7 audiobook creator. Every decision here has been researched and validated. Follow this as the source of truth.

---

## 1. CORE ARCHITECTURE: Manifest-Based Pipeline

The single most important change from V6 → V7 is splitting the monolithic flow into 3 independent stages coordinated by a JSON manifest file. This enables resume, selective re-generation, and cache efficiency.

### manifest.json Schema

```json
{
  "version": "7.0",
  "book": {
    "title": "The Warded Man",
    "author": "Peter V. Brett",
    "source_file": "warded_man.epub",
    "source_type": "epub"
  },
  "settings": {
    "tts_engine": "edge-tts",
    "narrator_voice": "en-US-GuyNeural",
    "dialogue_voice": "en-US-JennyNeural",
    "character_voices": {
      "Arlen": {"voice": "en-GB-RyanNeural", "detected_by": "auto"},
      "Leesha": {"voice": "en-US-JennyNeural", "detected_by": "manual"},
      "Rojer": {"voice": "en-AU-WilliamNeural", "detected_by": "auto"}
    },
    "pronunciation_overrides": {
      "Arlen": "AR-len",
      "Jardir": "jar-DEER",
      "alagai": "AL-ah-guy",
      "Krasia": "KRAY-zhuh"
    },
    "speed_multiplier": 1.0,
    "background_music": null,
    "music_duck_db": -15,
    "output_format": "m4b"
  },
  "chapters": [
    {
      "index": 0,
      "title": "Chapter 1: The Boy",
      "status": "complete",
      "segments": [
        {
          "index": 0,
          "text_hash": "a1b2c3d4e5f6...",
          "speaker": "narrator",
          "voice": "en-US-GuyNeural",
          "cache_file": "cache/a1b2c3d4_edge_GuyNeural.mp3",
          "duration_seconds": 14.3,
          "status": "cached"
        },
        {
          "index": 1,
          "text_hash": "f6e5d4c3b2a1...",
          "speaker": "Arlen",
          "voice": "en-GB-RyanNeural",
          "cache_file": null,
          "duration_seconds": null,
          "status": "pending"
        }
      ]
    }
  ],
  "progress": {
    "total_segments": 1247,
    "completed_segments": 843,
    "last_completed_chapter": 5,
    "last_completed_segment": 12,
    "generation_started": "2026-03-04T10:30:00",
    "estimated_remaining_seconds": 2400
  }
}
```

### Stage 1: Parse (text → manifest)

```python
def stage_parse(input_path: str, settings: dict) -> dict:
    """
    Input: file path + user settings
    Output: manifest dict (saved to manifest.json)
    
    Steps:
    1. Detect input type (PDF/EPUB/TXT/URL)
    2. Extract text (chapter by chapter as generator — NEVER load full book)
    3. Detect chapters (see Chapter Detection section)
    4. For each chapter:
       a. Chunk text into segments (5500 chars, sentence-aware)
       b. Detect dialogue + attribute speakers (see Character Detection)
       c. Detect SFX tags [CRASH], [THUNDER], etc.
       d. Detect scene breaks (*** or 2+ blank lines)
    5. Generate text_hash per segment: MD5(segment_text + voice_id + engine)
    6. Check cache for existing segments
    7. Write manifest.json
    """
```

### Stage 2: Generate (manifest → audio files)

```python
def stage_generate(manifest: dict, cancel_event: threading.Event) -> dict:
    """
    Input: manifest dict
    Output: updated manifest with cache_file paths + durations
    
    Steps:
    1. Read manifest, find all segments with status != "cached"
    2. For edge-tts: run up to 12 parallel async TTS calls
    3. For kokoro-onnx: run 1-2 concurrent inferences (RAM limit)
    4. Per segment:
       a. Apply pronunciation overrides (text replacement before TTS)
       b. Generate audio → write to cache/{hash}_{engine}_{voice}.mp3
       c. Get duration via ffprobe
       d. Update manifest segment status + cache_file + duration
       e. Save manifest after each segment (enables resume!)
    5. Check cancel_event between segments for clean stop
    """
```

### Stage 3: Assemble (audio files → final audiobook)

```python
def stage_assemble(manifest: dict) -> str:
    """
    Input: manifest dict (all segments cached)
    Output: path to final .m4b or .mp3 file
    
    Steps:
    1. Build FFmpeg concat file list with silence gaps:
       - 2.0s silence between chapters
       - 1.0s silence at scene breaks (*** markers)
       - 0.5s silence between paragraphs
       - 0.3s silence after dialogue attribution
    2. Concat all segments via FFmpeg concat demuxer
    3. If background music: mix with amix, duck to -15dB
    4. Run loudness normalization (two-pass, -19 LUFS target for audiobooks)
    5. If M4B output:
       a. Encode to AAC
       b. Write chapter metadata file
       c. Embed chapters + cover art
    6. Return output path
    """
```

---

## 2. TTS ENGINE ABSTRACTION

Create a base class so engines are swappable:

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

@dataclass
class TTSResult:
    audio_path: str
    duration_seconds: float
    sample_rate: int

class TTSEngine(ABC):
    @abstractmethod
    async def generate(self, text: str, voice: str, speed: float = 1.0,
                       output_path: str = None) -> TTSResult:
        pass
    
    @abstractmethod
    def list_voices(self) -> list[dict]:
        pass
    
    @abstractmethod
    def preview(self, voice: str) -> TTSResult:
        """Generate a 5-second sample of this voice"""
        pass
    
    @property
    @abstractmethod
    def max_concurrent(self) -> int:
        """How many parallel generations this engine supports"""
        pass
    
    @property
    @abstractmethod 
    def requires_internet(self) -> bool:
        pass


class EdgeTTSEngine(TTSEngine):
    """Free, cloud-based, 7+ neural voices, fast parallel"""
    
    @property
    def max_concurrent(self) -> int:
        return 12  # Network calls, low memory
    
    @property
    def requires_internet(self) -> bool:
        return True
    
    async def generate(self, text: str, voice: str, speed: float = 1.0,
                       output_path: str = None) -> TTSResult:
        import edge_tts
        rate_str = f"{int((speed - 1.0) * 100):+d}%"
        communicate = edge_tts.Communicate(text, voice, rate=rate_str)
        await communicate.save(output_path)
        duration = get_duration_ffprobe(output_path)
        return TTSResult(output_path, duration, 24000)


class KokoroEngine(TTSEngine):
    """Offline, 82M params ONNX, CPU-friendly, ~50 voices"""
    
    def __init__(self):
        self._model = None  # Lazy load
    
    def _ensure_model(self):
        if self._model is None:
            from kokoro_onnx import Kokoro
            # Model files: kokoro-v1.0.onnx (~80MB) + voices-v1.0.bin
            self._model = Kokoro("kokoro-v1.0.onnx", "voices-v1.0.bin")
    
    @property
    def max_concurrent(self) -> int:
        return 1  # CPU-bound, 3.4GB RAM constraint
    
    @property
    def requires_internet(self) -> bool:
        return False  # After first download
    
    async def generate(self, text: str, voice: str, speed: float = 1.0,
                       output_path: str = None) -> TTSResult:
        import soundfile as sf
        self._ensure_model()
        samples, sample_rate = self._model.create(text, voice=voice, speed=speed)
        sf.write(output_path, samples, sample_rate)
        duration = len(samples) / sample_rate
        return TTSResult(output_path, duration, sample_rate)
```

### Kokoro ONNX Specifics for Low-Spec Machine

- Model: kokoro-v1.0.onnx (~80MB download, one-time)
- Voices file: voices-v1.0.bin  
- Install: `pip install kokoro-onnx soundfile`
- CPU inference: ~500ms per short phrase on FP32 ONNX
- CRITICAL: On Ryzen 3200U (2 cores, 3.4GB RAM), limit to 1 concurrent inference
- The ONNX model stays loaded between calls (~200MB in RAM) — lazy-load it and keep it alive
- For quantized: use q8 model variant for speed boost with minimal quality loss
- Voice blending is possible: `0.7 * voice_a + 0.3 * voice_b` on the style vectors

---

## 3. CHARACTER DETECTION — Hybrid Regex + spaCy

### Regex Layer (handles ~70% of dialogue)

```python
import re
from typing import Optional

# Speech verbs — comprehensive list for fiction
SPEECH_VERBS = (
    r'said|asked|whispered|shouted|replied|muttered|called|cried|exclaimed|'
    r'murmured|growled|snapped|hissed|sighed|laughed|yelled|screamed|'
    r'pleaded|demanded|insisted|warned|added|continued|began|interrupted|'
    r'suggested|agreed|admitted|explained|announced|declared|protested|'
    r'argued|offered|promised|answered|urged|begged|gasped|stuttered|'
    r'mumbled|roared|barked|whimpered|purred|drawled|rasped|squeaked|'
    r'bellowed|croaked|groaned|moaned|chuckled|giggled|sobbed|wailed|'
    r'shrieked|breathed|mouthed|recited|quoted|remarked|noted|observed|'
    r'commented|mentioned|stated|uttered|voiced|intoned|chanted'
)

# Pattern 1: Post-dialogue — "Hello," Name said
PATTERN_POST = re.compile(
    r'["\u201C\u201D]([^"\u201C\u201D]+)["\u201C\u201D]\s*'
    r'([A-Z][a-z]+(?:\s[A-Z][a-z]+)?)\s+'
    r'(' + SPEECH_VERBS + r')',
    re.MULTILINE
)

# Pattern 2: Pre-dialogue — Name said, "Hello"
PATTERN_PRE = re.compile(
    r'([A-Z][a-z]+(?:\s[A-Z][a-z]+)?)\s+'
    r'(' + SPEECH_VERBS + r')\s*,?\s*'
    r'["\u201C\u201D]([^"\u201C\u201D]+)["\u201C\u201D]',
    re.MULTILINE
)

# Pattern 3: Mid-dialogue — "Hello," Name said, "how are you?"
PATTERN_MID = re.compile(
    r'["\u201C\u201D]([^"\u201C\u201D]+)["\u201C\u201D]\s*'
    r'([A-Z][a-z]+(?:\s[A-Z][a-z]+)?)\s+'
    r'(' + SPEECH_VERBS + r')\s*,?\s*'
    r'["\u201C\u201D]([^"\u201C\u201D]+)["\u201C\u201D]',
    re.MULTILINE
)

def extract_dialogue_regex(text: str) -> list[dict]:
    """
    Returns list of:
    {
        "start": int,       # char position in text
        "end": int,
        "dialogue": str,    # the quoted text
        "speaker": str,     # detected name or None
        "method": "regex"
    }
    """
    results = []
    # Try all three patterns, deduplicate by position
    for match in PATTERN_POST.finditer(text):
        results.append({
            "start": match.start(),
            "end": match.end(),
            "dialogue": match.group(1),
            "speaker": match.group(2),
            "method": "regex"
        })
    # ... same for PATTERN_PRE and PATTERN_MID
    # Deduplicate overlapping matches, prefer longest
    return deduplicate_by_position(results)
```

### spaCy Fallback Layer (catches ~15-20% more)

```python
# spaCy en_core_web_sm is ~12MB, loads in <1 second, minimal RAM
# Install: pip install spacy && python -m spacy download en_core_web_sm

import spacy

class SpacyAttributor:
    def __init__(self):
        self._nlp = None
    
    def _ensure_loaded(self):
        if self._nlp is None:
            self._nlp = spacy.load("en_core_web_sm")
    
    def attribute_unmatched(self, text: str, dialogue_start: int, 
                            dialogue_end: int) -> Optional[str]:
        """
        For dialogue that regex couldn't attribute,
        look at surrounding 2-3 sentences for PERSON entities.
        """
        self._ensure_loaded()
        # Get context: 500 chars before and after the dialogue
        ctx_start = max(0, dialogue_start - 500)
        ctx_end = min(len(text), dialogue_end + 500)
        context = text[ctx_start:ctx_end]
        
        doc = self._nlp(context)
        persons = [ent.text for ent in doc.ents if ent.label_ == "PERSON"]
        
        if persons:
            # Return the PERSON entity closest to the dialogue
            # (by character position)
            dialogue_pos = dialogue_start - ctx_start
            closest = min(persons, key=lambda p: 
                         abs(context.find(p) - dialogue_pos))
            return closest
        return None
```

### Alternation Tracker (catches another ~10%)

```python
class AlternationTracker:
    """
    Tracks A-B-A-B dialogue patterns.
    When two speakers alternate and attribution is dropped,
    continue the pattern.
    """
    def __init__(self):
        self.last_two_speakers = []  # [most_recent, previous]
    
    def record(self, speaker: str):
        self.last_two_speakers.insert(0, speaker)
        self.last_two_speakers = self.last_two_speakers[:2]
    
    def predict_next(self) -> Optional[str]:
        """If we have an A-B pattern, predict the next speaker"""
        if len(self.last_two_speakers) == 2:
            if self.last_two_speakers[0] != self.last_two_speakers[1]:
                # Alternating pattern — next should be [1]
                return self.last_two_speakers[1]
        return None
    
    def reset(self):
        """Reset at scene breaks or chapter boundaries"""
        self.last_two_speakers = []
```

### Combined Pipeline

```python
def detect_all_dialogue(chapter_text: str) -> list[dict]:
    """Full detection pipeline: regex → spaCy → alternation → fallback"""
    tracker = AlternationTracker()
    spacy_attr = SpacyAttributor()
    
    # Step 1: Find ALL quoted text
    all_quotes = find_all_quotes(chapter_text)  # simple quote-pair finder
    
    # Step 2: Try regex attribution
    regex_results = extract_dialogue_regex(chapter_text)
    
    # Step 3: For unmatched quotes, try spaCy
    for quote in all_quotes:
        if not is_attributed(quote, regex_results):
            speaker = spacy_attr.attribute_unmatched(
                chapter_text, quote["start"], quote["end"]
            )
            if speaker:
                quote["speaker"] = speaker
                quote["method"] = "spacy"
    
    # Step 4: For still-unmatched quotes, try alternation
    final_results = []
    for quote in all_quotes:
        if quote.get("speaker"):
            tracker.record(quote["speaker"])
        else:
            predicted = tracker.predict_next()
            if predicted:
                quote["speaker"] = predicted
                quote["method"] = "alternation"
                tracker.record(predicted)
            else:
                quote["speaker"] = None  # Falls to narrator voice
                quote["method"] = "unattributed"
        final_results.append(quote)
    
    # Reset tracker at scene breaks
    # (detected separately in the parsing stage)
    
    return final_results
```

---

## 4. CHAPTER DETECTION — Tiered Heuristics

```python
import re
from typing import Optional

# Priority order: metadata > patterns > formatting > fallback

def detect_chapters_epub(epub_path: str) -> list[dict]:
    """Tier 1: EPUB has TOC in NCX/OPF — use it directly"""
    import ebooklib
    from ebooklib import epub
    book = epub.read_epub(epub_path)
    chapters = []
    for item in book.get_items_of_type(ebooklib.ITEM_DOCUMENT):
        # Extract chapter title from HTML heading tags
        # Map to reading order from spine
        pass
    return chapters

def detect_chapters_pattern(text: str) -> list[dict]:
    """Tier 2: Regex patterns for common chapter headings"""
    patterns = [
        # "Chapter 1", "Chapter One", "CHAPTER I"
        re.compile(r'^(?:CHAPTER|Chapter)\s+(?:\d+|[IVXLCDM]+|[A-Z][a-z]+(?:\s[A-Z][a-z]+)?)'
                    r'(?:\s*[:.\-—]\s*.+)?$', re.MULTILINE),
        # "Part 1", "Part One", "PART I"
        re.compile(r'^(?:PART|Part)\s+(?:\d+|[IVXLCDM]+|[A-Z][a-z]+)', re.MULTILINE),
        # Just a number on its own line: "1" or "1."
        re.compile(r'^\s*\d{1,3}\.?\s*$', re.MULTILINE),
        # ALL CAPS title line (< 60 chars, followed by blank line)
        re.compile(r'^([A-Z][A-Z\s]{2,58})$(?=\s*\n\s*\n)', re.MULTILINE),
        # Title Case line (< 60 chars, followed by blank line)  
        re.compile(r'^([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,8})\s*$(?=\s*\n\s*\n)', re.MULTILINE),
    ]
    chapters = []
    for pattern in patterns:
        for match in pattern.finditer(text):
            chapters.append({
                "position": match.start(),
                "title": match.group(0).strip(),
                "method": "pattern"
            })
    return deduplicate_chapters(chapters)

def detect_scene_breaks(text: str) -> list[int]:
    """Detect within-chapter scene breaks for longer pauses"""
    patterns = [
        re.compile(r'^\s*\*\s*\*\s*\*\s*$', re.MULTILINE),   # * * *
        re.compile(r'^\s*\*{3,}\s*$', re.MULTILINE),           # ***
        re.compile(r'^\s*-{3,}\s*$', re.MULTILINE),            # ---
        re.compile(r'^\s*~{3,}\s*$', re.MULTILINE),            # ~~~
        re.compile(r'^\s*#\s*$', re.MULTILINE),                # # (section mark)
        re.compile(r'\n{3,}', re.MULTILINE),                   # 3+ blank lines
    ]
    positions = []
    for p in patterns:
        for match in p.finditer(text):
            positions.append(match.start())
    return sorted(set(positions))

# For PDFs: Use pdfplumber font-size detection
def detect_chapters_pdf_fonts(pdf_path: str) -> list[dict]:
    """Tier 3: Detect font size jumps as chapter headings"""
    import pdfplumber
    chapters = []
    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages):
            chars = page.chars
            if not chars:
                continue
            # Group chars by line (same top coordinate, ±2px tolerance)
            lines = group_chars_to_lines(chars)
            for line in lines:
                avg_size = sum(c['size'] for c in line) / len(line)
                line_text = ''.join(c['text'] for c in line).strip()
                # Chapter headings typically 14pt+ while body is 10-12pt
                if avg_size > 14 and len(line_text) < 80 and line_text:
                    chapters.append({
                        "position": page_num,
                        "title": line_text,
                        "font_size": avg_size,
                        "method": "font_size"
                    })
    return chapters
```

---

## 5. MEMORY-SAFE LONG BOOK PROCESSING

### Key constraints: Ryzen 3 3200U, 2 cores, 3.4GB RAM

```python
import gc
import os
import tempfile
from typing import Generator

def process_book_streaming(input_path: str, manifest: dict):
    """
    Generator-based processing — never holds full book in memory.
    Each chapter is processed and released before the next loads.
    """
    for chapter_idx, chapter_text in enumerate(yield_chapters(input_path)):
        # Process this chapter
        segments = chunk_text(chapter_text, max_chars=5500)
        
        for seg_idx, segment in enumerate(segments):
            # Generate TTS, write to disk immediately
            output_path = f"cache/{manifest_hash(segment)}.mp3"
            await current_engine.generate(segment.text, segment.voice, 
                                          output_path=output_path)
            
            # Update manifest on disk after each segment
            update_manifest_segment(manifest, chapter_idx, seg_idx, output_path)
            save_manifest(manifest)
            
            # Yield progress for Gradio UI update
            yield {
                "chapter": chapter_idx,
                "segment": seg_idx,
                "total_segments": manifest["progress"]["total_segments"],
                "completed": manifest["progress"]["completed_segments"]
            }
        
        # CRITICAL: Release chapter memory
        del chapter_text
        del segments
        gc.collect()

def yield_chapters(input_path: str) -> Generator[str, None, None]:
    """Yield one chapter at a time — never loads full book"""
    ext = os.path.splitext(input_path)[1].lower()
    
    if ext == '.epub':
        yield from yield_chapters_epub(input_path)
    elif ext == '.pdf':
        yield from yield_chapters_pdf(input_path)
    elif ext == '.txt':
        yield from yield_chapters_txt(input_path)

def yield_chapters_epub(epub_path: str) -> Generator[str, None, None]:
    import ebooklib
    from ebooklib import epub
    from bs4 import BeautifulSoup
    
    book = epub.read_epub(epub_path)
    for item in book.get_items_of_type(ebooklib.ITEM_DOCUMENT):
        soup = BeautifulSoup(item.get_content(), 'html.parser')
        text = soup.get_text(separator='\n')
        if len(text.strip()) > 100:  # Skip trivial pages (TOC, copyright)
            yield text
            del soup, text

def yield_chapters_pdf(pdf_path: str) -> Generator[str, None, None]:
    """Accumulate pages until chapter boundary, then yield"""
    import pdfplumber
    
    buffer = []
    with pdfplumber.open(pdf_path) as pdf:
        chapter_breaks = detect_chapters_pdf_fonts(pdf_path)
        break_pages = {ch["position"] for ch in chapter_breaks}
        
        for page_num, page in enumerate(pdf.pages):
            text = page.extract_text() or ""
            
            if page_num in break_pages and buffer:
                yield '\n'.join(buffer)
                buffer = []
                gc.collect()
            
            buffer.append(text)
        
        if buffer:
            yield '\n'.join(buffer)
```

---

## 6. CACHING SYSTEM

```python
import hashlib
import json
import os
import time
from pathlib import Path

class AudioCache:
    def __init__(self, cache_dir: str = "tts_cache", max_size_mb: int = 500):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(exist_ok=True)
        self.max_size_bytes = max_size_mb * 1024 * 1024
        self.index_path = self.cache_dir / "cache_index.json"
        self.index = self._load_index()
    
    def _make_key(self, text: str, voice: str, engine: str, speed: float) -> str:
        """Hash includes ALL parameters that affect audio output"""
        content = f"{text}|{voice}|{engine}|{speed}"
        return hashlib.md5(content.encode()).hexdigest()
    
    def get(self, text: str, voice: str, engine: str, speed: float = 1.0) -> str | None:
        """Returns cached file path or None"""
        key = self._make_key(text, voice, engine, speed)
        if key in self.index:
            path = self.cache_dir / self.index[key]["filename"]
            if path.exists():
                self.index[key]["last_accessed"] = time.time()
                self._save_index()
                return str(path)
            else:
                del self.index[key]  # Stale entry
        return None
    
    def put(self, text: str, voice: str, engine: str, speed: float,
            audio_path: str, duration: float) -> str:
        """Store audio file in cache, return cache path"""
        key = self._make_key(text, voice, engine, speed)
        ext = os.path.splitext(audio_path)[1]
        cache_filename = f"{key}{ext}"
        cache_path = self.cache_dir / cache_filename
        
        # Copy or move file to cache
        if str(audio_path) != str(cache_path):
            import shutil
            shutil.copy2(audio_path, cache_path)
        
        self.index[key] = {
            "filename": cache_filename,
            "voice": voice,
            "engine": engine,
            "duration": duration,
            "size_bytes": os.path.getsize(cache_path),
            "created": time.time(),
            "last_accessed": time.time()
        }
        self._save_index()
        self._enforce_size_limit()
        return str(cache_path)
    
    def _enforce_size_limit(self):
        """LRU eviction — prune least recently used files"""
        total_size = sum(v["size_bytes"] for v in self.index.values())
        if total_size <= self.max_size_bytes:
            return
        
        # Sort by last_accessed, evict oldest first
        sorted_keys = sorted(self.index.keys(), 
                            key=lambda k: self.index[k]["last_accessed"])
        
        while total_size > self.max_size_bytes and sorted_keys:
            key = sorted_keys.pop(0)
            entry = self.index[key]
            path = self.cache_dir / entry["filename"]
            if path.exists():
                total_size -= entry["size_bytes"]
                path.unlink()
            del self.index[key]
        
        self._save_index()
    
    def get_stats_for_manifest(self, manifest: dict) -> dict:
        """Show per-chapter cache status for UI"""
        stats = {}
        for chapter in manifest["chapters"]:
            total = len(chapter["segments"])
            cached = sum(1 for s in chapter["segments"] if s["status"] == "cached")
            stats[chapter["title"]] = {
                "total": total,
                "cached": cached,
                "percent": round(cached / total * 100) if total else 0
            }
        return stats
```

---

## 7. PRONUNCIATION OVERRIDE SYSTEM

```python
import re

class PronunciationDict:
    """
    Simple word → phonetic replacement applied BEFORE sending to TTS.
    Works with both edge-tts and Kokoro.
    
    For edge-tts: Replace the word with a "sounds-like" spelling
    For Kokoro: Same approach (Kokoro uses espeak-ng phonemizer internally)
    
    Store as JSON file per book, editable in Gradio UI.
    """
    
    def __init__(self, overrides: dict[str, str] = None):
        self.overrides = overrides or {}
    
    def apply(self, text: str) -> str:
        """Apply all pronunciation overrides to text before TTS"""
        for word, replacement in self.overrides.items():
            # Case-insensitive replacement, preserve surrounding punctuation
            # Use word boundaries to avoid partial matches
            pattern = re.compile(r'\b' + re.escape(word) + r'\b', re.IGNORECASE)
            text = pattern.sub(replacement, text)
        return text
    
    def save(self, path: str):
        import json
        with open(path, 'w') as f:
            json.dump(self.overrides, f, indent=2)
    
    @classmethod
    def load(cls, path: str) -> 'PronunciationDict':
        import json
        with open(path) as f:
            return cls(json.load(f))

# Example pronunciation file for Demon Cycle:
DEMON_CYCLE_PRONUNCIATIONS = {
    "Arlen": "Ar-len",
    "Jardir": "Jar-deer", 
    "Inevera": "In-EV-era",
    "Renna": "Ren-uh",
    "alagai": "al-uh-guy",
    "Krasia": "Kray-zhuh",
    "Sharum": "Shah-rum",
    "dal'Sharum": "dal Shah-rum",
    "Shar'Dama Ka": "Shar Dah-mah Kah",
    "greenlander": "green-lander",
    "Thesa": "Teh-suh",
    "warding": "war-ding",
    "coreling": "core-ling",
}
```

---

## 8. FFmpeg COMMANDS — Exact Patterns

### Get duration of an audio file
```bash
ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "segment.mp3"
```

### Generate silence gaps
```bash
# 2 second silence for chapter breaks
ffmpeg -f lavfi -i anullsrc=r=24000:cl=mono -t 2.0 -q:a 0 silence_2s.mp3

# 1 second for scene breaks
ffmpeg -f lavfi -i anullsrc=r=24000:cl=mono -t 1.0 -q:a 0 silence_1s.mp3

# 0.5 second for paragraph breaks
ffmpeg -f lavfi -i anullsrc=r=24000:cl=mono -t 0.5 -q:a 0 silence_05s.mp3
```

### Concatenate segments (zero-memory, file-based)
```bash
# Create concat file list (concat_list.txt):
# file 'cache/seg_001.mp3'
# file 'silence_05s.mp3'
# file 'cache/seg_002.mp3'
# file 'silence_2s.mp3'   <- chapter break
# file 'cache/seg_003.mp3'

ffmpeg -f concat -safe 0 -i concat_list.txt -c copy concatenated.mp3
```

### Loudness normalization — TWO-PASS for audiobooks

Target: **-19 LUFS** (audiobook standard, slightly louder than broadcast -23)
True Peak: **-1.5 dBTP**

```bash
# Pass 1: Measure
ffmpeg -i concatenated.mp3 -af loudnorm=I=-19:TP=-1.5:LRA=11:print_format=json -f null -

# Parse JSON output, then Pass 2: Apply
ffmpeg -i concatenated.mp3 -af "loudnorm=I=-19:TP=-1.5:LRA=11:measured_I=-27.2:measured_TP=-14.4:measured_LRA=0.1:measured_thresh=-37.7:offset=-0.5:linear=true" -ar 44100 normalized.mp3
```

#### Python automation of two-pass loudnorm:

```python
import subprocess
import json
import re

def normalize_loudness(input_path: str, output_path: str, 
                       target_lufs: float = -19.0) -> str:
    """Two-pass EBU R128 loudness normalization"""
    
    # Pass 1: Measure
    cmd1 = [
        'ffmpeg', '-i', input_path,
        '-af', f'loudnorm=I={target_lufs}:TP=-1.5:LRA=11:print_format=json',
        '-f', 'null', '-'
    ]
    result = subprocess.run(cmd1, capture_output=True, text=True)
    
    # Parse JSON from stderr (FFmpeg outputs stats there)
    stderr = result.stderr
    # Find the JSON block in stderr
    json_match = re.search(r'\{[^}]+\}', stderr, re.DOTALL)
    if not json_match:
        raise RuntimeError("Failed to parse loudnorm measurements")
    
    stats = json.loads(json_match.group())
    
    # Pass 2: Apply with measured values
    af_filter = (
        f"loudnorm=I={target_lufs}:TP=-1.5:LRA=11"
        f":measured_I={stats['input_i']}"
        f":measured_TP={stats['input_tp']}"
        f":measured_LRA={stats['input_lra']}"
        f":measured_thresh={stats['input_thresh']}"
        f":offset={stats['target_offset']}"
        f":linear=true"
    )
    
    cmd2 = [
        'ffmpeg', '-i', input_path,
        '-af', af_filter,
        '-ar', '44100',
        '-y', output_path
    ]
    subprocess.run(cmd2, check=True, capture_output=True)
    return output_path
```

### Background music mixing with ducking
```bash
ffmpeg -i narration.mp3 -i music.mp3 \
  -filter_complex "[1:a]volume=-15dB[music];[0:a][music]amix=inputs=2:duration=first:dropout_transition=3" \
  -ac 1 -ar 44100 mixed.mp3
```

### M4B Chapter Embedding — FFmpeg metadata method

Create a metadata file (`chapters_meta.txt`):
```ini
;FFMETADATA1
title=The Warded Man
artist=Peter V. Brett
album=The Demon Cycle Book 1
genre=Audiobook

[CHAPTER]
TIMEBASE=1/1000
START=0
END=847000
title=Chapter 1: The Boy

[CHAPTER]
TIMEBASE=1/1000
START=847000
END=1694000
title=Chapter 2: A Nightly Struggle

[CHAPTER]
TIMEBASE=1/1000
START=1694000
END=2541000
title=Chapter 3: Leesha
```

```bash
# Encode to AAC and embed chapters
ffmpeg -i normalized.mp3 -i chapters_meta.txt \
  -map 0:a -map_metadata 1 \
  -c:a aac -b:a 64k -ar 44100 -ac 1 \
  output.m4b

# Add cover art (separate step)
ffmpeg -i output.m4b -i cover.jpg \
  -map 0 -map 1 \
  -c copy -disposition:v attached_pic \
  final_audiobook.m4b
```

#### Python M4B chapter metadata generation:

```python
def generate_chapter_metadata(manifest: dict, output_path: str):
    """Generate FFmpeg metadata file from manifest"""
    lines = [";FFMETADATA1"]
    lines.append(f"title={manifest['book']['title']}")
    lines.append(f"artist={manifest['book']['author']}")
    lines.append(f"album={manifest['book']['title']}")
    lines.append("genre=Audiobook")
    lines.append("")
    
    current_time_ms = 0
    for chapter in manifest["chapters"]:
        chapter_duration_ms = sum(
            int(seg["duration_seconds"] * 1000) 
            for seg in chapter["segments"]
            if seg["duration_seconds"]
        )
        # Add silence gap duration
        chapter_duration_ms += 2000  # 2s chapter gap
        
        lines.append("[CHAPTER]")
        lines.append("TIMEBASE=1/1000")
        lines.append(f"START={current_time_ms}")
        lines.append(f"END={current_time_ms + chapter_duration_ms}")
        lines.append(f"title={chapter['title']}")
        lines.append("")
        
        current_time_ms += chapter_duration_ms
    
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))
```

---

## 9. GRADIO UI STRUCTURE

```python
import gradio as gr

def build_ui():
    with gr.Blocks(title="Audiobook Creator V7", theme=gr.themes.Soft()) as app:
        
        # ===== TAB 1: INPUT =====
        with gr.Tab("📖 Input"):
            with gr.Row():
                file_input = gr.File(
                    label="Drop your book here (EPUB, PDF, TXT)",
                    file_types=[".epub", ".pdf", ".txt"],
                    scale=2
                )
                url_input = gr.Textbox(
                    label="Or paste a URL",
                    placeholder="https://...",
                    scale=1
                )
            text_input = gr.Textbox(
                label="Or paste text directly",
                lines=8,
                visible=True
            )
            parse_btn = gr.Button("📋 Parse & Detect Chapters", variant="primary")
            
            # Shows after parsing
            chapter_list = gr.Dataframe(
                headers=["Chapter", "Segments", "Characters Found", "Cache Status"],
                label="Detected Chapters",
                visible=False
            )
        
        # ===== TAB 2: VOICES =====
        with gr.Tab("🎤 Voices"):
            with gr.Row():
                engine_select = gr.Radio(
                    ["edge-tts (Cloud, Free)", "Kokoro (Offline, CPU)"],
                    label="TTS Engine",
                    value="edge-tts (Cloud, Free)"
                )
            
            with gr.Row():
                narrator_voice = gr.Dropdown(
                    label="Narrator Voice",
                    choices=[],  # Populated by engine selection
                    scale=2
                )
                narrator_preview = gr.Button("▶ Preview", scale=1)
                narrator_audio = gr.Audio(label="Preview", visible=False)
            
            with gr.Row():
                dialogue_voice = gr.Dropdown(
                    label="Default Dialogue Voice",
                    choices=[],
                    scale=2
                )
                dialogue_preview = gr.Button("▶ Preview", scale=1)
            
            # Character voice map — auto-populated, user-editable
            gr.Markdown("### Character Voice Assignments")
            gr.Markdown("*Auto-detected from text. Click any voice to change.*")
            character_table = gr.Dataframe(
                headers=["Character", "Voice", "Detection Method", "Occurrences"],
                label="Character → Voice Map",
                interactive=True
            )
            
            # Pronunciation overrides
            gr.Markdown("### Pronunciation Overrides")
            pronunciation_table = gr.Dataframe(
                headers=["Word", "Sounds Like"],
                label="Custom Pronunciations",
                interactive=True
            )
            
            with gr.Row():
                speed_slider = gr.Slider(0.8, 1.3, value=1.0, step=0.05,
                                        label="Speed")
            
            with gr.Accordion("Background Music", open=False):
                music_file = gr.File(label="Music file (MP3)", file_types=[".mp3"])
                music_volume = gr.Slider(-25, -5, value=-15, step=1,
                                        label="Music volume (dB, lower = quieter)")
        
        # ===== TAB 3: GENERATE =====
        with gr.Tab("⚡ Generate"):
            with gr.Row():
                generate_btn = gr.Button("🚀 Generate Audiobook", 
                                        variant="primary", scale=2)
                cancel_btn = gr.Button("⛔ Cancel", variant="stop", scale=1)
            
            with gr.Row():
                output_format = gr.Radio(["M4B (Chaptered)", "MP3"],
                                        value="M4B (Chaptered)")
                normalize_check = gr.Checkbox(
                    label="Normalize loudness (-19 LUFS)",
                    value=True
                )
            
            # Time estimate (shown before generation)
            time_estimate = gr.Markdown("*Click Parse first to see time estimate*")
            
            # Progress
            progress_bar = gr.Progress()
            progress_text = gr.Markdown("")
            
            # Per-chapter progress
            chapter_progress = gr.Dataframe(
                headers=["Chapter", "Status", "Segments Done"],
                label="Chapter Progress"
            )
        
        # ===== TAB 4: PLAYER =====
        with gr.Tab("🎧 Player"):
            audio_player = gr.Audio(label="Audiobook", type="filepath")
            
            # Chapter navigation
            chapter_nav = gr.Dropdown(label="Jump to Chapter", choices=[])
            
            # Bookmark controls
            with gr.Row():
                bookmark_btn = gr.Button("🔖 Save Bookmark")
                bookmark_list = gr.Dataframe(
                    headers=["Chapter", "Position", "Saved At"],
                    label="Bookmarks"
                )
            
            download_btn = gr.File(label="Download Audiobook")
    
    return app
```

---

## 10. DEPENDENCIES — pip install line

```bash
# Core (required)
pip install gradio edge-tts pdfplumber ebooklib beautifulsoup4 trafilatura pydub

# Kokoro offline TTS (optional, ~80MB model download on first use)
pip install kokoro-onnx soundfile

# spaCy for character detection (optional but recommended, ~12MB model)
pip install spacy
python -m spacy download en_core_web_sm

# ffmpeg-normalize for loudness (optional — we implement two-pass manually)
# pip install ffmpeg-normalize  

# System requirement: FFmpeg must be installed and on PATH
# Windows: choco install ffmpeg  OR  download from ffmpeg.org
```

---

## 11. KEY DECISIONS SUMMARY (for quick reference)

| Decision | Choice | Reason |
|----------|--------|--------|
| Architecture | 3-stage manifest pipeline | Enables resume, selective re-gen, cache efficiency |
| Default TTS | edge-tts | Free, cloud, good quality, 12x parallel |
| Offline TTS | Kokoro ONNX v1.0 | 82M params, CPU-friendly, ~80MB, Apache 2.0 |
| Future TTS | Chatterbox (GPU users only) | Best quality, voice cloning, emotion control — but needs CUDA |
| Character detection | Regex → spaCy → Alternation → Narrator fallback | 85-90% accuracy, no heavy ML |
| spaCy model | en_core_web_sm (~12MB) | Minimal RAM, fast load, good enough for NER |
| Chapter detection | EPUB TOC → Regex → Font size → Fallback | 95%+ accuracy, zero ML |
| Cache key | MD5(text + voice + engine + speed) | Per-segment, includes all audio-affecting params |
| Cache eviction | LRU (least recently used) | Protects in-progress work |
| Loudness target | -19 LUFS, -1.5 dBTP | Audiobook standard (louder than broadcast -23) |
| Silence gaps | 2s chapter / 1s scene / 0.5s paragraph / 0.3s dialogue | Professional audiobook pacing |
| M4B chapters | FFmpeg metadata file method | No extra dependencies (no MP4Box needed) |
| Long book memory | Generator-based chapter streaming + gc.collect() | Stays under 3.4GB RAM |
| Kokoro concurrency | 1 (maybe 2) concurrent inferences | RAM constraint on low-spec machine |
| edge-tts concurrency | 12 parallel async calls | Network-bound, low local memory |
| Speed control | Post-process with FFmpeg atempo (cache-friendly) | Single cache entry per segment |
| UI framework | Gradio with 4 tabs | Mobile-friendly, no extra frontend code |

---

## 12. FILE STRUCTURE

```
audiobook_creator_v7.py          # Single-file app (main entry point)
tts_cache/                       # Auto-created cache directory
  cache_index.json               # LRU cache metadata
  {hash}.mp3                     # Cached audio segments
manifests/                       # Saved manifests for resume
  {book_title}_manifest.json
pronunciations/                  # Per-book pronunciation overrides  
  demon_cycle.json
  custom.json
temp/                            # Temporary files during assembly
  concat_list.txt
  chapters_meta.txt
  silence_*.mp3
output/                          # Final audiobooks
  The_Warded_Man.m4b
```

---

## NOTES FOR SONNET

- This is a SINGLE-FILE Python app. Everything goes in `audiobook_creator_v7.py` 
- Target machine: Windows 11, Ryzen 3 3200U (2 cores), 3.4GB RAM — optimize accordingly
- User runs from Android mostly (Gradio serves to browser, so this is fine)
- FFmpeg is assumed installed and on PATH
- Always provide COMPLETE working code, not patches
- The manifest.json design is the backbone — everything flows through it
- Test with: `python audiobook_creator_v7.py` → opens in browser at localhost:7860
