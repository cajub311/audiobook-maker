from __future__ import annotations

import gc
import re
from pathlib import Path
from typing import Any, Callable, Optional
from urllib.parse import urlparse

from config import DEFAULT_SEGMENT_CHUNK_CHARS, MAX_UPLOAD_FILE_BYTES


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

SCENE_BREAK_PATTERNS = [
    re.compile(r"^\s*\*\s*\*\s*\*\s*$", re.MULTILINE),
    re.compile(r"^\s*\*{3,}\s*$", re.MULTILINE),
    re.compile(r"^\s*-{3,}\s*$", re.MULTILINE),
    re.compile(r"^\s*~{3,}\s*$", re.MULTILINE),
    re.compile(r"^\s*#\s*$", re.MULTILINE),
    re.compile(r"\n{3,}", re.MULTILINE),
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


def chunk_text(text: str, max_chars: int = DEFAULT_SEGMENT_CHUNK_CHARS) -> list[str]:
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


def validate_local_input_file(path: Path, max_upload_file_bytes: int = MAX_UPLOAD_FILE_BYTES) -> None:
    if not path.exists() or not path.is_file():
        raise ValueError("Uploaded file could not be found. Please upload it again.")
    size_bytes = int(path.stat().st_size)
    if size_bytes > max_upload_file_bytes:
        max_mb = max_upload_file_bytes // (1024 * 1024)
        size_mb = size_bytes / (1024 * 1024)
        raise ValueError(
            f"File is too large ({size_mb:.1f} MB). Maximum allowed is {max_mb} MB. "
            "Try a smaller file, split the book, or raise ABM_MAX_UPLOAD_FILE_BYTES if you host privately."
        )


def extract_source_chapters(
    input_path: Optional[str] = None,
    url: Optional[str] = None,
    raw_text: Optional[str] = None,
    *,
    extract_text_from_url_fn: Callable[[str], str],
    validate_local_input_file_fn: Optional[Callable[[Path], None]] = None,
) -> tuple[list[dict[str, str]], dict[str, str], str, str]:
    if raw_text and raw_text.strip():
        chapters = split_text_into_chapters(raw_text.strip())
        return chapters, {"title": "Pasted Text", "author": "Unknown"}, "inline_text", "text"

    if url and url.strip():
        text = extract_text_from_url_fn(url.strip())
        chapters = split_text_into_chapters(text)
        host = urlparse(url).netloc or "url"
        return chapters, {"title": f"Web Import - {host}", "author": "Unknown"}, url, "url"

    if not input_path:
        raise ValueError("No input provided. Upload a file, enter a URL, or paste text.")
    path = Path(input_path)
    file_validator = validate_local_input_file_fn or validate_local_input_file
    file_validator(path)
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
