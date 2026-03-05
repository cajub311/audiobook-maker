"""
src_text_processor.py — Text processing module for Audiobook Creator V7

Handles book parsing (epub/pdf/txt/url), chapter detection, text chunking,
character detection, voice mapping, pronunciation overrides, and book analysis.
"""

from __future__ import annotations

import json
import logging
import os
import re
from collections import Counter
from typing import Generator, Optional

logger = logging.getLogger(__name__)

# =============================================================================
# 1. BOOK INPUT PARSERS
# =============================================================================


def _html_to_text(html_content: str) -> tuple[str, Optional[str]]:
    """
    Convert HTML content to plain text, also extracting the first heading.

    Returns (plain_text, heading_or_None).
    """
    try:
        from bs4 import BeautifulSoup  # type: ignore
    except ImportError:
        text = re.sub(r"<[^>]+>", " ", html_content)
        return re.sub(r" {2,}", " ", text).strip(), None

    soup = BeautifulSoup(html_content, "html.parser")
    title = None
    for tag in ("h1", "h2", "h3"):
        heading = soup.find(tag)
        if heading:
            title = heading.get_text(strip=True)
            break

    text = soup.get_text(separator="\n")
    return text.strip(), title


def yield_chapters_epub(epub_path: str) -> Generator[dict, None, None]:
    """
    Yield chapters from an EPUB file one at a time.

    Each yielded dict contains:
        - 'title': chapter title extracted from h1/h2/h3, or 'Chapter N'
        - 'text': plain text content
        - 'index': 0-based chapter index

    Skips TOC pages, copyright pages, and items shorter than 200 chars.
    """
    try:
        import ebooklib  # type: ignore
        from ebooklib import epub  # type: ignore
    except ImportError as exc:
        raise ImportError(
            "ebooklib and beautifulsoup4 are required for EPUB parsing. "
            f"Install with: pip install ebooklib beautifulsoup4\nCause: {exc}"
        ) from exc

    _TOC_MARKERS = frozenset(
        {"table of contents", "copyright", "all rights reserved", "published by"}
    )

    book = epub.read_epub(epub_path)
    chapter_index = 0

    for item in book.get_items_of_type(ebooklib.ITEM_DOCUMENT):
        raw = item.get_content()
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8", errors="replace")

        text, title = _html_to_text(raw)
        stripped = text.strip()

        if len(stripped) < 200:
            continue

        sample = stripped[:400].lower()
        if any(marker in sample for marker in _TOC_MARKERS) and len(stripped) < 1500:
            continue

        yield {
            "title": title or f"Chapter {chapter_index + 1}",
            "text": stripped,
            "index": chapter_index,
        }
        chapter_index += 1


def _is_chapter_heading(text: str) -> bool:
    """Return True if the text looks like a chapter or section heading."""
    if not text or len(text) > 120:
        return False
    lower = text.lower().strip()
    if re.match(
        r"^(chapter|part|book|section|prologue|epilogue|introduction|preface|"
        r"afterword|interlude|foreword|acknowledgment)",
        lower,
    ):
        return True
    if re.match(r"^\d{1,3}[\.\s]", text.strip()):
        return True
    if re.match(r"^[IVXLCDM]{1,6}[\.\s]", text.strip()):
        return True
    return False


def yield_chapters_pdf(pdf_path: str) -> Generator[dict, None, None]:
    """
    Yield chapters from a PDF file using pdfplumber.

    Detects chapter breaks by identifying lines where the average font size
    exceeds 14pt and the text matches a chapter-heading pattern.
    """
    try:
        import pdfplumber  # type: ignore
    except ImportError as exc:
        raise ImportError(
            "pdfplumber is required for PDF parsing. "
            f"Install with: pip install pdfplumber\nCause: {exc}"
        ) from exc

    chapter_index = 0
    current_title = "Chapter 1"
    current_lines: list[str] = []

    def _flush(title: str, lines: list[str], idx: int) -> Optional[dict]:
        body = "\n".join(lines).strip()
        if len(body) < 200:
            return None
        return {"title": title, "text": body, "index": idx}

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            words = page.extract_words(extra_attrs=["size"])
            if not words:
                plain = page.extract_text() or ""
                if plain:
                    current_lines.append(plain)
                continue

            # Group words into visual lines by y-coordinate proximity
            lines_on_page: list[list[dict]] = []
            line_buf: list[dict] = []
            prev_top: Optional[float] = None

            for word in words:
                top = word.get("top", 0.0)
                if prev_top is None or abs(top - prev_top) < 4:
                    line_buf.append(word)
                    prev_top = top
                else:
                    if line_buf:
                        lines_on_page.append(line_buf)
                    line_buf = [word]
                    prev_top = top
            if line_buf:
                lines_on_page.append(line_buf)

            for line_words in lines_on_page:
                avg_size = sum(w.get("size", 12.0) for w in line_words) / len(line_words)
                line_text = " ".join(w.get("text", "") for w in line_words).strip()

                if avg_size > 14.0 and _is_chapter_heading(line_text):
                    result = _flush(current_title, current_lines, chapter_index)
                    if result:
                        yield result
                        chapter_index += 1
                    current_title = line_text
                    current_lines = []
                else:
                    current_lines.append(line_text)

    result = _flush(current_title, current_lines, chapter_index)
    if result:
        yield result


# =============================================================================
# Chapter heading regex patterns (5 patterns)
# =============================================================================

_ORDINAL_WORDS = (
    r"(?:One|Two|Three|Four|Five|Six|Seven|Eight|Nine|Ten|Eleven|Twelve|"
    r"Thirteen|Fourteen|Fifteen|Sixteen|Seventeen|Eighteen|Nineteen|Twenty|"
    r"Thirty|Forty|Fifty|Sixty|Seventy|Eighty|Ninety|Hundred|"
    r"First|Second|Third|Fourth|Fifth|Sixth|Seventh|Eighth|Ninth|Tenth)"
)

CHAPTER_PATTERNS: list[re.Pattern] = [
    # Pattern 1 — "Chapter N" / "Chapter One" with optional subtitle (same line only)
    re.compile(
        rf"^(Chapter[ \t]+(?:\d+|[IVXLCDM]{{1,7}}|{_ORDINAL_WORDS}"
        rf"(?:[-\s](?:and\s+)?{_ORDINAL_WORDS})?))"
        r"[ \t:–—\-]*([^\n]{0,80})?$",
        re.IGNORECASE | re.MULTILINE,
    ),
    # Pattern 2 — "Part N" / "Part One" etc.
    re.compile(
        rf"^(Part[ \t]+(?:\d+|[IVXLCDM]{{1,7}}|{_ORDINAL_WORDS}))[ \t:–—\-]*([^\n]{{0,80}})?$",
        re.IGNORECASE | re.MULTILINE,
    ),
    # Pattern 3 — All-caps special section names standing alone on a line
    re.compile(
        r"^(PROLOGUE|EPILOGUE|INTERLUDE|INTRODUCTION|PREFACE|FOREWORD|"
        r"AFTERWORD|ACKNOWLEDGMENTS?|APPENDIX(?:\s+\w+)?|GLOSSARY|"
        r"CODA|ENVOI|NOTE\s+(?:TO|FROM)\s+THE\s+AUTHOR)$",
        re.MULTILINE,
    ),
    # Pattern 4 — Numeric or Roman numeral headings: "1." / "IV." / "42  Title"
    re.compile(
        r"^(\d{1,3}|[IVXLCDM]{1,7})\.[ \t]+[A-Z\"\u201c]",
        re.MULTILINE,
    ),
    # Pattern 5 — Scene-break / section-marker lines: ***, ---, ~~~, # # #
    re.compile(
        r"^[ \t]*(?:\*{3,}|[-]{3,}|[~]{3,}|[#]{3,}|[=]{3,}|\* \* \*|— — —)[ \t]*$",
        re.MULTILINE,
    ),
]


def detect_chapters_epub(epub_path: str) -> list[dict]:
    """
    Return a list of chapter dicts from an EPUB file.

    Each dict: {'title': str, 'text': str, 'index': int}
    """
    return list(yield_chapters_epub(epub_path))


def detect_chapters_pattern(text: str) -> list[dict]:
    """
    Detect chapters in plain text using CHAPTER_PATTERNS.

    Returns list of dicts:
        {'title': str, 'text': str, 'start': int, 'end': int, 'index': int}
    """
    hits: list[tuple[int, str]] = []

    for pattern in CHAPTER_PATTERNS:
        for m in pattern.finditer(text):
            raw_title = m.group(0).strip()
            if len(raw_title) > 80:
                raw_title = raw_title[:77] + "..."
            hits.append((m.start(), raw_title))

    if not hits:
        return []

    # Sort and deduplicate overlapping matches (keep first occurrence per window)
    hits.sort(key=lambda h: h[0])
    deduped: list[tuple[int, str]] = []
    for pos, title in hits:
        if deduped and pos - deduped[-1][0] < 5:
            continue
        deduped.append((pos, title))

    chapters: list[dict] = []
    for i, (pos, title) in enumerate(deduped):
        start = pos
        end = deduped[i + 1][0] if i + 1 < len(deduped) else len(text)
        slice_text = text[start:end]
        first_nl = slice_text.find("\n")
        body = slice_text[first_nl + 1 :] if first_nl != -1 else slice_text
        chapters.append(
            {
                "title": title,
                "text": body.strip(),
                "start": start,
                "end": end,
                "index": i,
            }
        )

    return chapters


def detect_chapters_pdf_fonts(pdf_path: str) -> list[dict]:
    """
    Detect chapters in a PDF by identifying large-font headings (> 14pt).

    Returns list of dicts: {'title': str, 'text': str, 'index': int}
    """
    return list(yield_chapters_pdf(pdf_path))


def detect_scene_breaks(text: str) -> list[int]:
    """
    Find character positions of scene breaks in the text.

    Scene breaks are lines containing only ***, ---, ~~~, ###, or similar
    decoration patterns.  Returns a sorted list of start positions.
    """
    pattern = re.compile(
        r"^[ \t]*(?:\*{3,}|[-]{3,}|[~]{3,}|[#]{3,}|[=]{3,}|\* \* \*|— — —)[ \t]*$",
        re.MULTILINE,
    )
    return [m.start() for m in pattern.finditer(text)]


def yield_chapters_txt(txt_path: str) -> Generator[dict, None, None]:
    """
    Yield chapters from a plain-text file by splitting on heading patterns.

    Falls back to yielding the entire file as a single chapter when no
    chapter markers are detected.
    """
    with open(txt_path, "r", encoding="utf-8", errors="replace") as fh:
        content = fh.read()

    chapters = detect_chapters_pattern(content)
    if not chapters:
        yield {
            "title": os.path.splitext(os.path.basename(txt_path))[0],
            "text": content.strip(),
            "index": 0,
        }
        return

    for chapter in chapters:
        if chapter["text"].strip():
            yield chapter


def fetch_and_parse_url(url: str) -> Generator[dict, None, None]:
    """
    Fetch a URL, extract main text with trafilatura, then split into chapters.

    Falls back to requests + BeautifulSoup when trafilatura is unavailable.
    """
    text: Optional[str] = None

    try:
        import trafilatura  # type: ignore

        downloaded = trafilatura.fetch_url(url)
        if downloaded:
            text = trafilatura.extract(
                downloaded,
                include_comments=False,
                include_tables=False,
                no_fallback=False,
            )
    except ImportError:
        logger.warning("trafilatura not available; falling back to requests + BeautifulSoup")

    if text is None:
        try:
            import requests  # type: ignore
            from bs4 import BeautifulSoup  # type: ignore

            resp = requests.get(url, timeout=30, headers={"User-Agent": "Mozilla/5.0"})
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")
            for tag in soup(["script", "style", "nav", "footer", "header"]):
                tag.decompose()
            text = soup.get_text(separator="\n")
        except ImportError as exc:
            raise ImportError(
                "trafilatura or (requests + beautifulsoup4) are required for URL parsing."
            ) from exc

    if not text or not text.strip():
        raise ValueError(f"Could not extract text from URL: {url}")

    chapters = detect_chapters_pattern(text)
    if not chapters:
        slug = url.rstrip("/").split("/")[-1] or "Article"
        yield {"title": slug, "text": text.strip(), "index": 0}
        return

    for chapter in chapters:
        if chapter["text"].strip():
            yield chapter


def yield_chapters(
    input_path: str, source_type: Optional[str] = None
) -> Generator[dict, None, None]:
    """
    Router: detect source type and delegate to the appropriate parser.

    Auto-detects from URL scheme or file extension when source_type is None.
    Supported values for source_type: 'epub', 'pdf', 'txt', 'url'.
    """
    if source_type is None:
        if re.match(r"^https?://", input_path, re.IGNORECASE):
            source_type = "url"
        else:
            ext = os.path.splitext(input_path)[1].lower()
            source_type = {
                ".epub": "epub",
                ".pdf": "pdf",
                ".txt": "txt",
                ".md": "txt",
                ".text": "txt",
            }.get(ext)

        if source_type is None:
            raise ValueError(
                f"Cannot determine source type for: {input_path!r}. "
                "Pass source_type='epub'|'pdf'|'txt'|'url' explicitly."
            )

    _parsers = {
        "epub": yield_chapters_epub,
        "pdf": yield_chapters_pdf,
        "txt": yield_chapters_txt,
        "url": fetch_and_parse_url,
    }

    parser = _parsers.get(source_type.lower())
    if parser is None:
        raise ValueError(
            f"Unknown source type: {source_type!r}. Choose from {list(_parsers)}"
        )

    yield from parser(input_path)


# =============================================================================
# 3. TEXT CHUNKING
# =============================================================================

_SFX_PATTERN = re.compile(r"\[([A-Z][A-Z0-9 _]*(?::\s*[^\]]+)?)\]")
_SCENE_BREAK_LINE = re.compile(
    r"^[ \t]*(?:\*{3,}|[-]{3,}|[~]{3,}|[#]{3,}|[=]{3,}|\* \* \*|— — —)[ \t]*$",
    re.MULTILINE,
)

# Abbreviations that should NOT trigger sentence splits
_ABBREV_PROTECT = (
    "Mr", "Mrs", "Ms", "Dr", "Prof", "Sr", "Jr", "Rev", "Gen", "Sgt",
    "Cpl", "Pvt", "Lt", "Capt", "Col", "Maj", "Adm", "Gov", "Sen",
    "Rep", "Pres", "St", "Ave", "Blvd", "Dept", "Est", "Inc", "Ltd",
    "Co", "Corp", "Jan", "Feb", "Mar", "Apr", "Jun", "Jul", "Aug",
    "Sep", "Oct", "Nov", "Dec", "vs", "etc", "ie", "eg", "al",
)
_ABBREV_RE = re.compile(
    r"\b(" + "|".join(re.escape(a) for a in _ABBREV_PROTECT) + r")\.",
    re.UNICODE,
)
# Two alternatives cover sentence-end punctuation with or without closing quote
_SENTENCE_SPLIT_RE = re.compile(
    r'(?<=[.!?]["\u201d])\s+(?=[A-Z\"\u201c])|(?<=[.!?])\s+(?=[A-Z\"\u201c])',
    re.UNICODE,
)


def _split_sentences(text: str) -> list[str]:
    """Split text into sentences using punctuation heuristics."""
    protected = _ABBREV_RE.sub(lambda m: m.group(1) + "\x00", text)
    parts = _SENTENCE_SPLIT_RE.split(protected)
    return [p.replace("\x00", ".").strip() for p in parts if p.strip()]


def chunk_text_smart(text: str, max_chars: int = 5500) -> list[dict]:
    """
    Split text into segments ≤ max_chars, always breaking at sentence boundaries.

    Returns a list of segment dicts:
    {
        'text': str,
        'segment_type': 'narration' | 'dialogue' | 'sfx' | 'scene_break',
        'is_scene_break': bool,
        'paragraph_end': bool,
    }

    Rules:
    - Never splits mid-sentence (falls back to word boundary only for extreme cases)
    - Detects SFX tags: [CRASH], [THUNDER], [MUSIC: melancholic]
    - Detects scene breaks (*** / --- / ~~~)
    - Marks paragraph boundaries (double newline)
    """
    if not text:
        return []

    segments: list[dict] = []
    paragraphs = re.split(r"\n{2,}", text)

    for p_idx, paragraph in enumerate(paragraphs):
        paragraph = paragraph.strip()
        if not paragraph:
            continue

        is_last_para = p_idx == len(paragraphs) - 1

        # Scene break paragraph
        if _SCENE_BREAK_LINE.match(paragraph):
            segments.append(
                {
                    "text": paragraph,
                    "segment_type": "scene_break",
                    "is_scene_break": True,
                    "paragraph_end": True,
                }
            )
            continue

        # SFX-only paragraph
        if _SFX_PATTERN.fullmatch(paragraph.strip()):
            segments.append(
                {
                    "text": paragraph,
                    "segment_type": "sfx",
                    "is_scene_break": False,
                    "paragraph_end": True,
                }
            )
            continue

        # Determine default segment type for this paragraph
        stripped = paragraph.strip()
        seg_type = (
            "dialogue"
            if stripped.startswith(('"', "\u201c", "'"))
            else "narration"
        )

        # Paragraph fits in a single chunk
        if len(paragraph) <= max_chars:
            segments.append(
                {
                    "text": paragraph,
                    "segment_type": seg_type,
                    "is_scene_break": False,
                    "paragraph_end": not is_last_para,
                }
            )
            continue

        # Paragraph too long — split at sentence boundaries
        sentences = _split_sentences(paragraph)
        chunk_sentences: list[str] = []
        chunk_len = 0

        for sentence in sentences:
            s_len = len(sentence) + 1  # +1 for the rejoining space

            # SFX standalone sentence — flush current chunk first
            if _SFX_PATTERN.fullmatch(sentence.strip()):
                if chunk_sentences:
                    segments.append(
                        {
                            "text": " ".join(chunk_sentences),
                            "segment_type": seg_type,
                            "is_scene_break": False,
                            "paragraph_end": False,
                        }
                    )
                    chunk_sentences = []
                    chunk_len = 0
                segments.append(
                    {
                        "text": sentence.strip(),
                        "segment_type": "sfx",
                        "is_scene_break": False,
                        "paragraph_end": False,
                    }
                )
                continue

            # Flush when adding this sentence would exceed limit
            if chunk_len + s_len > max_chars and chunk_sentences:
                segments.append(
                    {
                        "text": " ".join(chunk_sentences),
                        "segment_type": seg_type,
                        "is_scene_break": False,
                        "paragraph_end": False,
                    }
                )
                chunk_sentences = []
                chunk_len = 0

            # Sentence itself exceeds max_chars — hard-split at word boundary
            if len(sentence) > max_chars:
                words = sentence.split()
                word_buf: list[str] = []
                word_len = 0
                for word in words:
                    wl = len(word) + 1
                    if word_len + wl > max_chars and word_buf:
                        segments.append(
                            {
                                "text": " ".join(word_buf),
                                "segment_type": seg_type,
                                "is_scene_break": False,
                                "paragraph_end": False,
                            }
                        )
                        word_buf = []
                        word_len = 0
                    word_buf.append(word)
                    word_len += wl
                if word_buf:
                    chunk_sentences.extend(word_buf)
                    chunk_len += word_len
            else:
                chunk_sentences.append(sentence)
                chunk_len += s_len

        if chunk_sentences:
            segments.append(
                {
                    "text": " ".join(chunk_sentences),
                    "segment_type": seg_type,
                    "is_scene_break": False,
                    "paragraph_end": not is_last_para,
                }
            )

    return segments


# =============================================================================
# 4. CHARACTER DETECTION — FULL PIPELINE
# =============================================================================

SPEECH_VERBS = (
    r"said|asked|replied|answered|whispered|shouted|cried|exclaimed|muttered|"
    r"murmured|added|continued|interrupted|snapped|growled|hissed|laughed|"
    r"sighed|called|announced|declared|demanded|pleaded|begged|urged|insisted|"
    r"suggested|warned|threatened|promised|admitted|confessed|agreed|disagreed|"
    r"protested|objected|argued|explained|described|stated|noted|observed|"
    r"remarked|commented|mentioned|reported|claimed|denied|confirmed|"
    r"acknowledged|emphasized|stressed|repeated|echoed|responded|retorted|"
    r"countered|challenged|questioned|wondered|mused|breathed|panted|gasped|"
    r"choked|stammered|stuttered|faltered|hesitated|began|finished|started|"
    r"ended|resumed|proceeded|thought|realized|remembered|recalled|called|"
    r"hollered|barked|bellowed|boomed|drawled|droned|faltered|moaned|"
    r"pleaded|roared|scoffed|screeched|sneered|sobbed|taunted|teased|"
    r"urged|vowed|wailed|whimpered|yelled"
)

_NAME_RE = r"[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2}"
_OPEN_Q = r'["\u201c]'
_CLOSE_Q = r'["\u201d]'
_DIALOGUE_RE = rf"{_OPEN_Q}([^\"'\u201d]{{1,400}}){_CLOSE_Q}"

# "Hello," Name said  /  "Hello." Name said
PATTERN_POST = re.compile(
    rf"{_OPEN_Q}([^\"\u201d]{{1,400}}){_CLOSE_Q}[,.]?\s+({_NAME_RE})\s+(?:{SPEECH_VERBS})",
    re.UNICODE,
)

# Name said, "Hello"  /  Name said "Hello"
PATTERN_PRE = re.compile(
    rf"({_NAME_RE})\s+(?:{SPEECH_VERBS})[^\"\u201c\u201d]{{0,40}}{_OPEN_Q}([^\"\u201d]{{1,400}}){_CLOSE_Q}",
    re.UNICODE,
)

# "Hello," Name said, "how are you?"
PATTERN_MID = re.compile(
    rf"{_OPEN_Q}([^\"\u201d]{{1,200}}){_CLOSE_Q}[,.]?\s+({_NAME_RE})\s+(?:{SPEECH_VERBS})"
    rf"[^\"\u201c\u201d]{{0,40}}{_OPEN_Q}([^\"\u201d]{{1,200}}){_CLOSE_Q}",
    re.UNICODE,
)

_NON_CHARACTER_WORDS = frozenset(
    {
        "He", "She", "They", "We", "You", "It", "I", "A", "The", "An",
        "This", "That", "These", "Those", "My", "Your", "His", "Her",
        "Its", "Our", "Their", "What", "Who", "Which", "When", "Where",
        "Why", "How", "All", "Any", "Each", "Every", "Both", "Neither",
        "Either", "Some", "Many", "Few", "More", "Most", "Such", "No",
        "Not", "Only", "Own", "Same", "So", "Than", "Too", "Very",
        "Just", "Here", "There", "Now", "Back", "Then", "Once",
        "Monday", "Tuesday", "Wednesday", "Thursday", "Friday",
        "Saturday", "Sunday",
        "January", "February", "March", "April", "May", "June", "July",
        "August", "September", "October", "November", "December",
        "North", "South", "East", "West", "God", "Lord", "The",
    }
)


def find_all_quotes(text: str) -> list[dict]:
    """
    Find all quoted text spans in text.

    Returns list of dicts:
        {'text': str, 'start': int, 'end': int, 'quote_index': int}
    """
    pattern = re.compile(
        rf"{_OPEN_Q}([^\"\u201d]{{1,500}}){_CLOSE_Q}", re.UNICODE
    )
    return [
        {
            "text": m.group(1),
            "start": m.start(),
            "end": m.end(),
            "quote_index": i,
        }
        for i, m in enumerate(pattern.finditer(text))
    ]


def is_attributed(quote: dict, results: list[dict]) -> bool:
    """Return True if the quote already has a speaker attribution in results."""
    for r in results:
        if r.get("start") == quote.get("start") and r.get("speaker"):
            return True
    return False


def deduplicate_by_position(results: list[dict]) -> list[dict]:
    """
    Remove duplicate dialogue detections at the same start position.

    When duplicates exist, prefers the result that has a speaker attribution.
    """
    seen: dict[int, dict] = {}
    for r in results:
        pos = r.get("start", 0)
        if pos not in seen:
            seen[pos] = r
        elif r.get("speaker") and not seen[pos].get("speaker"):
            seen[pos] = r
    return sorted(seen.values(), key=lambda x: x.get("start", 0))


def extract_dialogue_regex(text: str) -> list[dict]:
    """
    Extract dialogue and speaker attributions using the three regex patterns.

    Returns list of dicts:
    {
        'dialogue': str,
        'speaker': str | None,
        'start': int,
        'end': int,
        'method': 'regex_post' | 'regex_pre' | 'regex_mid',
    }
    """
    results: list[dict] = []

    for m in PATTERN_MID.finditer(text):
        speaker = m.group(2).strip()
        if speaker in _NON_CHARACTER_WORDS:
            continue
        results.append(
            {
                "dialogue": m.group(1).strip() + " " + m.group(3).strip(),
                "speaker": speaker,
                "start": m.start(),
                "end": m.end(),
                "method": "regex_mid",
            }
        )

    for m in PATTERN_POST.finditer(text):
        speaker = m.group(2).strip()
        if speaker in _NON_CHARACTER_WORDS:
            continue
        results.append(
            {
                "dialogue": m.group(1).strip(),
                "speaker": speaker,
                "start": m.start(),
                "end": m.end(),
                "method": "regex_post",
            }
        )

    for m in PATTERN_PRE.finditer(text):
        speaker = m.group(1).strip()
        if speaker in _NON_CHARACTER_WORDS:
            continue
        results.append(
            {
                "dialogue": m.group(2).strip(),
                "speaker": speaker,
                "start": m.start(),
                "end": m.end(),
                "method": "regex_pre",
            }
        )

    return deduplicate_by_position(results)


class SpacyAttributor:
    """
    Uses spaCy NER to attribute unmatched dialogue to nearby named entities.

    Gracefully degrades when spaCy or an English model is unavailable.
    """

    def __init__(self) -> None:
        self._nlp = None
        self._available: Optional[bool] = None

    def _load(self) -> bool:
        if self._available is not None:
            return self._available
        try:
            import spacy  # type: ignore

            for model_name in ("en_core_web_sm", "en_core_web_md", "en_core_web_lg"):
                try:
                    self._nlp = spacy.load(model_name)
                    self._available = True
                    return True
                except OSError:
                    continue
            logger.warning(
                "No spaCy English model found. "
                "Run: python -m spacy download en_core_web_sm"
            )
            self._available = False
            return False
        except ImportError:
            logger.warning(
                "spaCy not installed. Character attribution relies on regex only."
            )
            self._available = False
            return False

    def attribute_unmatched(
        self, text: str, dialogue_start: int, dialogue_end: int
    ) -> Optional[str]:
        """
        Attempt to attribute dialogue at [dialogue_start:dialogue_end] using
        PERSON entities found in the surrounding 300-character context window.

        Returns the most-recently-mentioned person name, or None.
        """
        if not self._load():
            return None

        ctx_start = max(0, dialogue_start - 300)
        ctx_end = min(len(text), dialogue_end + 300)
        context = text[ctx_start:ctx_end]

        doc = self._nlp(context)  # type: ignore[misc]
        dialogue_offset = dialogue_start - ctx_start

        candidates: list[tuple[int, str]] = [
            (ent.start_char, ent.text.strip())
            for ent in doc.ents
            if ent.label_ == "PERSON"
            and ent.start_char <= dialogue_offset
            and ent.text.strip() not in _NON_CHARACTER_WORDS
        ]

        if not candidates:
            return None

        candidates.sort(key=lambda x: x[0], reverse=True)
        return candidates[0][1]


class AlternationTracker:
    """
    Predicts the next speaker in unattributed dialogue by tracking
    alternation patterns in the recent conversation history.
    """

    def __init__(self, window: int = 6) -> None:
        self._history: list[str] = []
        self._window = window

    def record(self, speaker: str) -> None:
        """Record a confirmed speaker turn."""
        self._history.append(speaker)
        if len(self._history) > self._window * 2:
            self._history = self._history[-(self._window * 2) :]

    def predict_next(self) -> Optional[str]:
        """
        Predict the next speaker based on recent alternation history.

        Uses the two most recently active speakers; if the last recorded
        speaker is A, predicts B (the other alternating participant).
        Returns None when history is insufficient.
        """
        if len(self._history) < 2:
            return None

        last = self._history[-1]
        recent = self._history[-self._window :]
        # Unique speakers in reverse-recency order
        seen: dict[str, None] = {}
        for s in reversed(recent):
            seen[s] = None
        unique = list(seen.keys())

        if len(unique) >= 2 and unique[0] == last:
            return unique[1]
        return None

    def reset(self) -> None:
        """Clear the alternation history."""
        self._history.clear()


def detect_all_dialogue(chapter_text: str) -> list[dict]:
    """
    Full dialogue detection pipeline:

    1. Regex pattern matching (PATTERN_MID → PATTERN_POST → PATTERN_PRE)
    2. spaCy NER for quotes not matched by regex
    3. Alternation prediction for still-unmatched quotes
    4. Fallback: assign 'Narrator' as speaker

    Processing is done in text order so the alternation tracker builds
    incrementally as dialogue is discovered.

    Returns list of dicts:
    {
        'dialogue': str,
        'speaker': str,
        'start': int,
        'end': int,
        'method': 'regex_post'|'regex_pre'|'regex_mid'|'spacy'|'alternation'|'narrator',
    }
    """
    all_quotes = find_all_quotes(chapter_text)
    regex_results = extract_dialogue_regex(chapter_text)
    regex_by_start = {r["start"]: r for r in regex_results}

    tracker = AlternationTracker()
    spacy_attr = SpacyAttributor()
    final: list[dict] = []

    for quote in sorted(all_quotes, key=lambda q: q["start"]):
        # Regex already attributed this position
        if quote["start"] in regex_by_start:
            r = regex_by_start[quote["start"]]
            final.append(r)
            if r.get("speaker"):
                tracker.record(r["speaker"])
            continue

        # spaCy attribution
        speaker = spacy_attr.attribute_unmatched(
            chapter_text, quote["start"], quote["end"]
        )
        method = "spacy"

        # Alternation prediction fallback
        if not speaker:
            speaker = tracker.predict_next()
            method = "alternation"

        # Ultimate fallback
        if not speaker:
            speaker = "Narrator"
            method = "narrator"
        else:
            tracker.record(speaker)

        final.append(
            {
                "dialogue": quote["text"],
                "speaker": speaker,
                "start": quote["start"],
                "end": quote["end"],
                "method": method,
            }
        )

    return final


# =============================================================================
# 5. CHARACTER VOICE MAPPING
# =============================================================================


class CharacterRegistry:
    """
    Tracks all characters discovered across the book, assigns TTS voices,
    and records occurrence counts.

    The first voice in available_voices is always reserved for the Narrator.
    Remaining characters are assigned voices in descending frequency order
    so the most-spoken characters get the most distinctive voices first.
    """

    def __init__(self, available_voices: list[str]) -> None:
        self._available_voices: list[str] = list(available_voices)
        self._narrator_voice: str = available_voices[0] if available_voices else "default"
        self._characters: dict[str, dict] = {}

    # ------------------------------------------------------------------
    # Mutation helpers
    # ------------------------------------------------------------------

    def register(
        self, name: str, method: str = "unknown", context_snippet: str = ""
    ) -> None:
        """Register one occurrence of a character."""
        if name not in self._characters:
            self._characters[name] = {
                "name": name,
                "occurrences": 0,
                "voice": None,
                "detection_method": method,
                "context_snippets": [],
            }
        self._characters[name]["occurrences"] += 1
        snippets = self._characters[name]["context_snippets"]
        if context_snippet and len(snippets) < 3:
            snippets.append(context_snippet[:120])

    def assign_voice(self, name: str, voice: str) -> None:
        """Manually assign a TTS voice to a character."""
        if name not in self._characters:
            self.register(name)
        self._characters[name]["voice"] = voice

    def auto_assign_voices(self) -> None:
        """
        Automatically assign voices from the available pool.

        The Narrator always receives the first available voice.
        Other characters are assigned from the remaining pool in
        descending order of occurrence count; voices cycle when the
        pool is exhausted.
        """
        if "Narrator" in self._characters:
            self._characters["Narrator"]["voice"] = self._narrator_voice

        unassigned = sorted(
            (
                (name, data)
                for name, data in self._characters.items()
                if name != "Narrator" and data["voice"] is None
            ),
            key=lambda x: x[1]["occurrences"],
            reverse=True,
        )

        pool = [v for v in self._available_voices if v != self._narrator_voice]
        if not pool:
            pool = self._available_voices

        for i, (name, _) in enumerate(unassigned):
            self._characters[name]["voice"] = pool[i % len(pool)]

    # ------------------------------------------------------------------
    # Read helpers
    # ------------------------------------------------------------------

    def get_voice(self, name: str) -> str:
        """Return the assigned voice for name, falling back to the narrator voice."""
        char = self._characters.get(name)
        if char and char.get("voice"):
            return char["voice"]
        return self._narrator_voice

    def get_top_characters(self, n: int = 20) -> list[dict]:
        """Return the top N characters sorted by occurrence count."""
        return sorted(
            self._characters.values(),
            key=lambda c: c["occurrences"],
            reverse=True,
        )[:n]

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        """Serialise registry to a plain dict (for manifest storage)."""
        return {
            "available_voices": self._available_voices,
            "narrator_voice": self._narrator_voice,
            "characters": self._characters,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "CharacterRegistry":
        """Deserialise a CharacterRegistry from a plain dict."""
        registry = cls(available_voices=data.get("available_voices", ["default"]))
        registry._narrator_voice = data.get("narrator_voice", registry._narrator_voice)
        registry._characters = data.get("characters", {})
        return registry

    def __len__(self) -> int:
        return len(self._characters)

    def __contains__(self, name: str) -> bool:
        return name in self._characters

    def __repr__(self) -> str:
        return f"CharacterRegistry({len(self._characters)} characters)"


# =============================================================================
# 6. PRONUNCIATION OVERRIDE SYSTEM
# =============================================================================

DEMON_CYCLE_PRONUNCIATIONS: dict[str, str] = {
    "Arlen": "AHR-len",
    "Inevera": "in-EV-er-ah",
    "Jardir": "JAR-deer",
    "Krasian": "KRAY-zhen",
    "Sharum": "shah-ROOM",
    "Deliverer": "deh-LIV-er-er",
    "Dama": "DAH-mah",
    "Khaffit": "khah-FEET",
    "Leesha": "LEE-shah",
    "Rojer": "ROH-jer",
    "Briar": "BREE-ar",
    "Sharak": "sha-RAHK",
    "Everam": "EV-er-ahm",
    "Nie": "NEE",
    "Angierian": "an-JEER-ee-en",
    "Tibbet": "TIH-bit",
    "Amanvah": "ah-MAN-vah",
    "Sikvah": "SIK-vah",
    "Enkido": "en-KEE-doh",
    "Aleverak": "al-EV-er-ak",
    "Jayan": "JAY-an",
}

WHEEL_OF_TIME_PRONUNCIATIONS: dict[str, str] = {
    "Aes Sedai": "EYES seh-DYE",
    "Nynaeve": "NYE-neev",
    "Egwene": "EHG-ween",
    "Moiraine": "mwah-RAIN",
    "Siuan": "SWAHN",
    "Gawyn": "GAY-win",
    "Elayne": "eh-LAYN",
    "Aviendha": "ah-vee-END-ah",
    "Birgitte": "bir-GEET",
    "Loial": "LOY-al",
    "ta'veren": "tah-VEER-en",
    "Trolloc": "TROL-ock",
    "Myrddraal": "MEER-drahl",
    "Saidar": "SAY-dar",
    "Saidin": "SAY-din",
    "Tuatha'an": "TWA-than",
    "Ogier": "OH-jeer",
    "Aiel": "EYE-eel",
    "Cairhien": "KEER-hee-en",
    "Andor": "AHN-dor",
    "Illian": "ILL-ee-an",
    "Seanchan": "SHAWN-chan",
    "Amadicia": "ah-mah-DEE-see-ah",
    "Tel'aran'rhiod": "tel-AH-ran-ree-OD",
    "Forsaken": "for-SAY-ken",
    "Perrin": "PEHR-in",
    "Rand": "RAND",
    "Tear": "TEER",
    "Tar Valon": "TAR val-ON",
    "Lan": "LAN",
}

DUNE_PRONUNCIATIONS: dict[str, str] = {
    "Muad'Dib": "MWAD-dib",
    "Bene Gesserit": "BEH-nee JESS-er-it",
    "Fremen": "FREE-men",
    "Harkonnen": "har-KON-nen",
    "Atreides": "ah-TRAY-deez",
    "Arrakis": "ah-RAK-iss",
    "Shai-Hulud": "shy-huh-LOOD",
    "Sardaukar": "sar-DAW-kar",
    "Kwisatz Haderach": "KWIS-ats HAD-er-ak",
    "Melange": "meh-LAWNZH",
    "Stilgar": "STIL-gar",
    "Chani": "CHAH-nee",
    "Ghanima": "gah-NEE-mah",
    "Leto": "LEE-toh",
    "Shadout Mapes": "sha-DOOT MAY-pez",
    "Alia": "AH-lee-ah",
    "Gurney Halleck": "GUR-nee HAL-ek",
    "Thufir Hawat": "THOO-feer hah-WAHT",
    "Mentat": "MEN-tat",
    "Fedaykin": "feh-DAY-kin",
    "Sietch": "SEETCH",
    "Caladan": "KAL-ah-dan",
    "Giedi Prime": "GEE-dee PRYME",
    "Thumper": "THUM-per",
}

_GENRE_PRESET_MAP: dict[str, dict[str, str]] = {
    "demon cycle": DEMON_CYCLE_PRONUNCIATIONS,
    "warded man": DEMON_CYCLE_PRONUNCIATIONS,
    "daylight war": DEMON_CYCLE_PRONUNCIATIONS,
    "skull throne": DEMON_CYCLE_PRONUNCIATIONS,
    "wheel of time": WHEEL_OF_TIME_PRONUNCIATIONS,
    "eye of the world": WHEEL_OF_TIME_PRONUNCIATIONS,
    "great hunt": WHEEL_OF_TIME_PRONUNCIATIONS,
    "dragon reborn": WHEEL_OF_TIME_PRONUNCIATIONS,
    "dune": DUNE_PRONUNCIATIONS,
    "messiah": DUNE_PRONUNCIATIONS,
    "children of dune": DUNE_PRONUNCIATIONS,
}


class PronunciationDict:
    """
    Manages pronunciation overrides for TTS text pre-processing.

    All replacements use word-boundary matching; multi-word phrases are
    sorted longest-first to prevent partial substitutions.
    """

    def __init__(self, overrides: Optional[dict[str, str]] = None) -> None:
        self._overrides: dict[str, str] = dict(overrides) if overrides else {}
        self._compiled: list[tuple[re.Pattern, str]] = []
        self._dirty = True

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _recompile(self) -> None:
        self._compiled = []
        for phrase in sorted(self._overrides, key=len, reverse=True):
            replacement = self._overrides[phrase]
            try:
                # Use look-around boundaries for phrases that contain
                # non-word characters (apostrophes, hyphens, spaces)
                escaped = re.escape(phrase)
                pattern = re.compile(
                    rf"(?<!\w){escaped}(?!\w)", re.IGNORECASE | re.UNICODE
                )
                self._compiled.append((pattern, replacement))
            except re.error as exc:
                logger.warning("Invalid pronunciation pattern for %r: %s", phrase, exc)
        self._dirty = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def add(self, word: str, pronunciation: str) -> None:
        """Add or update a single pronunciation override."""
        self._overrides[word] = pronunciation
        self._dirty = True

    def remove(self, word: str) -> None:
        """Remove a pronunciation override."""
        self._overrides.pop(word, None)
        self._dirty = True

    def apply(self, text: str) -> str:
        """Apply all overrides to text using compiled word-boundary patterns."""
        if self._dirty:
            self._recompile()
        for pattern, replacement in self._compiled:
            text = pattern.sub(replacement, text)
        return text

    def save(self, path: str) -> None:
        """Persist overrides to a JSON file."""
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(self._overrides, fh, indent=2, ensure_ascii=False)

    @classmethod
    def load(cls, path: str) -> "PronunciationDict":
        """Load overrides from a JSON file."""
        with open(path, "r", encoding="utf-8") as fh:
            overrides = json.load(fh)
        return cls(overrides=overrides)

    def suggest_for_book(self, title: str) -> dict:
        """
        Return a preset pronunciation dict based on keywords in the book title.

        Checks the title against known series keywords; returns an empty dict
        when no match is found.
        """
        lower = title.lower()
        for keyword, preset in _GENRE_PRESET_MAP.items():
            if keyword in lower:
                return dict(preset)
        return {}

    def __len__(self) -> int:
        return len(self._overrides)

    def __repr__(self) -> str:
        return f"PronunciationDict({len(self._overrides)} overrides)"


# =============================================================================
# 7. BOOK ANALYSIS
# =============================================================================


def analyze_book(chapters: list[dict]) -> dict:
    """
    Compute statistics for a list of chapter dicts.

    Returns:
    {
        'total_words': int,
        'total_chars': int,
        'estimated_duration_minutes': int,   # at ~130 wpm (audiobook pace)
        'chapter_count': int,
        'character_count': int,
        'top_characters': list[{'name': str, 'occurrences': int}],
        'dialogue_percentage': float,
        'has_sfx_tags': bool,
        'language': str,
    }
    """
    total_words = 0
    total_chars = 0
    total_dialogue_chars = 0
    character_counts: Counter = Counter()
    has_sfx = False
    lang_sample_parts: list[str] = []

    for chapter in chapters:
        text: str = chapter.get("text", "")
        if not text:
            continue

        total_words += len(text.split())
        total_chars += len(text)

        if len(lang_sample_parts) < 5:
            lang_sample_parts.append(text[:1000])

        if not has_sfx and _SFX_PATTERN.search(text):
            has_sfx = True

        for result in extract_dialogue_regex(text):
            total_dialogue_chars += len(result.get("dialogue", ""))
            speaker = result.get("speaker")
            if speaker and speaker != "Narrator":
                character_counts[speaker] += 1

    dialogue_pct = (
        round((total_dialogue_chars / total_chars) * 100, 2) if total_chars else 0.0
    )
    lang_sample = "\n".join(lang_sample_parts)
    language = detect_language(lang_sample) if lang_sample else "unknown"

    return {
        "total_words": total_words,
        "total_chars": total_chars,
        "estimated_duration_minutes": int(total_words / 130),
        "chapter_count": len(chapters),
        "character_count": len(character_counts),
        "top_characters": [
            {"name": name, "occurrences": count}
            for name, count in character_counts.most_common(20)
        ],
        "dialogue_percentage": dialogue_pct,
        "has_sfx_tags": has_sfx,
        "language": language,
    }


# =============================================================================
# 8. IMPROVEMENTS
# =============================================================================


def detect_emotion(text_segment: str) -> str:
    """
    Detect the emotional tone of a text segment using punctuation heuristics.

    Returns one of: 'normal' | 'excited' | 'questioning' | 'whisper' | 'shouting'

    Heuristics:
      - *whisper* / ~whisper~ / (whispered) → 'whisper'
      - 3+ exclamation marks OR 3+ consecutive ALL-CAPS words → 'shouting'
      - 2+ question marks or '???' → 'questioning'
      - 1-2 exclamation marks OR 1-2 ALL-CAPS words → 'excited'
      - Otherwise → 'normal'
    """
    # Whisper indicators
    if re.search(
        r"\*[^*]{1,80}\*|~[^~]{1,80}~|\(whisper(?:ed|ing|s)?\)",
        text_segment,
        re.IGNORECASE,
    ):
        return "whisper"

    excl_count = text_segment.count("!")
    quest_count = text_segment.count("?")
    caps_words = re.findall(r"\b[A-Z]{3,}\b", text_segment)

    if excl_count >= 3 or len(caps_words) >= 3:
        return "shouting"

    if quest_count >= 2 or "???" in text_segment:
        return "questioning"

    if excl_count >= 1 or len(caps_words) >= 1:
        return "excited"

    return "normal"


def apply_ssml_hints(text: str, emotion: str, voice_type: str = "narration") -> str:
    """
    Wrap text in SSML <prosody> tags appropriate for the detected emotion.

    Uses Microsoft Azure TTS / edge-tts SSML prosody attribute values:
      rate  : x-slow | slow | medium | fast | x-fast
      pitch : x-low  | low  | medium | high | x-high
      volume: x-soft | soft | medium | loud | x-loud

    When emotion is 'normal', returns the XML-escaped text unwrapped.

    Parameters
    ----------
    text:       Raw text segment to wrap.
    emotion:    Output of detect_emotion().
    voice_type: 'narration' or 'dialogue' — reserved for future tuning.
    """
    # XML-escape the content
    escaped = (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )

    _EMOTION_PROSODY: dict[str, dict[str, str]] = {
        "whisper": {"rate": "slow", "volume": "soft", "pitch": "low"},
        "shouting": {"rate": "fast", "volume": "x-loud", "pitch": "high"},
        "excited": {"rate": "fast", "volume": "loud"},
        "questioning": {"rate": "medium", "pitch": "high"},
    }

    params = _EMOTION_PROSODY.get(emotion)
    if not params:
        return escaped

    attrs = " ".join(f'{k}="{v}"' for k, v in params.items())
    return f"<prosody {attrs}>{escaped}</prosody>"


# Common function-word sets used for language detection heuristics
_LANG_MARKERS: dict[str, frozenset] = {
    "en": frozenset(
        {
            "the", "and", "of", "to", "a", "in", "is", "it", "you", "that",
            "he", "was", "for", "on", "are", "with", "as", "his", "they",
            "at", "be", "this", "have", "from", "or", "one", "had", "by",
            "but", "not", "what", "all", "were", "we", "when", "your", "can",
            "said", "there", "an", "each", "which", "she", "do", "how",
        }
    ),
    "de": frozenset(
        {
            "der", "die", "und", "in", "den", "von", "zu", "das", "mit",
            "sich", "des", "auf", "für", "ist", "im", "dem", "nicht", "ein",
            "eine", "als", "auch", "es", "an", "werden", "aus", "er", "hat",
            "dass", "sie", "nach", "wird", "bei", "noch", "war", "aber",
        }
    ),
    "fr": frozenset(
        {
            "le", "la", "les", "de", "du", "des", "un", "une", "et", "en",
            "que", "qui", "dans", "il", "elle", "nous", "vous", "ils",
            "se", "on", "par", "sur", "au", "aux", "est", "sont", "pas",
            "ne", "plus", "ou", "ce", "mais", "comme", "avoir", "leur",
        }
    ),
    "es": frozenset(
        {
            "el", "la", "de", "que", "y", "en", "los", "se", "del", "las",
            "un", "por", "con", "una", "su", "para", "es", "al", "lo",
            "como", "más", "pero", "sus", "le", "ya", "o", "fue", "este",
            "ha", "sino", "sobre", "ser", "bien", "me", "mi",
        }
    ),
    "it": frozenset(
        {
            "il", "di", "che", "e", "la", "in", "un", "per", "una",
            "del", "le", "si", "non", "dei", "con", "da", "al", "lo",
            "ho", "ci", "mi", "nel", "ma", "come", "sono", "gli",
            "anche", "nella", "lui", "sua", "ha", "loro", "più",
        }
    ),
    "pt": frozenset(
        {
            "de", "a", "o", "que", "e", "do", "da", "em", "um", "para",
            "é", "com", "uma", "os", "no", "se", "na", "por", "mais",
            "as", "dos", "das", "como", "mas", "foi", "ao", "ele",
            "das", "tem", "à", "seu", "sua",
        }
    ),
}


def detect_language(text: str) -> str:
    """
    Simple heuristic language detection using common function-word frequency.

    Checks up to the first 500 words against per-language word sets.
    Returns an ISO 639-1 code ('en', 'de', 'fr', 'es', 'it', 'pt') or
    'unknown' when confidence is too low.
    """
    if not text or len(text.strip()) < 20:
        return "unknown"

    words = re.findall(r"\b[a-z]{2,}\b", text.lower())
    if not words:
        return "unknown"

    sample = set(words[:500])
    scores = {lang: len(sample & markers) for lang, markers in _LANG_MARKERS.items()}
    best = max(scores, key=lambda k: scores[k])

    # Require at least 2 matching function words for confidence
    if scores[best] < 2:
        return "unknown"
    return best


# Abbreviation expansions: (compiled_pattern, replacement)
_ABBREV_EXPANSIONS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\bMr\.\s*(?=[A-Z])", re.UNICODE), "Mister "),
    (re.compile(r"\bMrs\.\s*(?=[A-Z])", re.UNICODE), "Missus "),
    (re.compile(r"\bMs\.\s*(?=[A-Z])", re.UNICODE), "Miss "),
    (re.compile(r"\bDr\.\s*(?=[A-Z])", re.UNICODE), "Doctor "),
    (re.compile(r"\bProf\.\s*(?=[A-Z])", re.UNICODE), "Professor "),
    (re.compile(r"\bSt\.\s*(?=[A-Z])", re.UNICODE), "Saint "),
    (re.compile(r"\bJr\b\.?", re.UNICODE), "Junior"),
    (re.compile(r"\bSr\b\.?", re.UNICODE), "Senior"),
    (re.compile(r"\bvs\.", re.IGNORECASE), "versus"),
    (re.compile(r"\betc\.", re.IGNORECASE), "et cetera"),
    (re.compile(r"\bi\.e\.", re.IGNORECASE), "that is"),
    (re.compile(r"\be\.g\.", re.IGNORECASE), "for example"),
    (re.compile(r"\bcf\.", re.IGNORECASE), "compare"),
    (re.compile(r"\bft\.", re.IGNORECASE), "feet"),
    (re.compile(r"\bin\.\s*(?=\d)", re.IGNORECASE), "inches "),
    (re.compile(r"\blb?s?\.", re.IGNORECASE), "pounds"),
    (re.compile(r"\boz\.", re.IGNORECASE), "ounces"),
    (re.compile(r"\bkm\b", re.IGNORECASE), "kilometers"),
    (re.compile(r"\bkph\b", re.IGNORECASE), "kilometers per hour"),
    (re.compile(r"\bmph\b", re.IGNORECASE), "miles per hour"),
    # Months — strip trailing dot so TTS reads "Jan" not "jan period"
    (
        re.compile(
            r"\b(Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\.",
            re.IGNORECASE,
        ),
        lambda m: m.group(1),  # type: ignore[arg-type]
    ),
]

# Character-level normalisation: (compiled_pattern, replacement)
_TTS_NORMALISE: list[tuple[re.Pattern, str]] = [
    (re.compile(r"[\u200b\u200c\u200d\ufeff]"), ""),          # zero-width chars
    (re.compile(r"\r\n|\r"), "\n"),                             # line-ending normalise
    (re.compile(r"\u00a0"), " "),                               # non-breaking space
    (re.compile(r"[ \t]{2,}"), " "),                            # collapse spaces/tabs
    (re.compile(r"\u2026"), "..."),                             # unicode ellipsis
    (re.compile(r"\.{4,}"), "..."),                             # 4+ dots → ellipsis
    (re.compile(r"[\u2018\u2019\u0060\u00b4]"), "'"),           # smart single quotes
    (re.compile(r"[\u201c\u201d\u00ab\u00bb]"), '"'),           # smart double quotes
    (re.compile(r"[\u2013\u2014\u2015]"), " - "),               # en/em dashes → ASCII hyphen
    (re.compile(r"\u2012"), "-"),                               # figure dash
    (re.compile(r"[\u2022\u2023\u25e6\u2043\u204c\u204d]"), " "),  # bullet points
    (re.compile(r"\u00b7"), " "),                               # middle dot
    (re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]"), ""),   # ASCII control chars
]


def clean_text_for_tts(text: str) -> str:
    """
    Clean and normalise text for TTS synthesis.

    Operations performed (in order):
    1. Remove zero-width / invisible / control characters
    2. Normalise smart quotes and dashes to ASCII equivalents
    3. Expand common abbreviations (Mr. → Mister, etc.)
    4. Normalise ellipsis sequences
    5. Collapse excess whitespace
    6. Convert ellipsis to a comma-pause for more natural TTS pacing

    Returns the cleaned string.
    """
    if not text:
        return ""

    # Character-level normalisation
    for pattern, replacement in _TTS_NORMALISE:
        text = pattern.sub(replacement, text)

    # Abbreviation expansion
    for pattern, replacement in _ABBREV_EXPANSIONS:
        if callable(replacement):
            text = pattern.sub(replacement, text)
        else:
            text = pattern.sub(replacement, text)

    # Convert ellipsis to a natural pause representation
    text = text.replace("...", ", ")

    # Final structural cleanup
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = text.strip()

    return text
