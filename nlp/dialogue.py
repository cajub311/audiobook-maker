from __future__ import annotations

import re
from typing import Any, Optional


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

QUOTE_STYLE_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("double", re.compile(r'"(.+?)"', re.DOTALL)),
    ("curly", re.compile(r"“(.+?)”", re.DOTALL)),
    ("guillemet", re.compile(r"«(.+?)»", re.DOTALL)),
    ("german", re.compile(r"„(.+?)“", re.DOTALL)),
    ("cjk_corner", re.compile(r"「(.+?)」", re.DOTALL)),
    ("cjk_double_corner", re.compile(r"『(.+?)』", re.DOTALL)),
]


def normalize_dialogue_strategy(value: str) -> str:
    low = (value or "").strip().lower()
    if "regex" in low:
        return "regex_only"
    if "quote" in low:
        return "quotes_only"
    return "auto"


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
                "confidence": 0.95,
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
                "confidence": 0.95,
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
                "confidence": 0.95,
            }
        )
    return deduplicate_by_position(results)


def find_all_quotes(text: str) -> list[dict[str, Any]]:
    quotes: list[dict[str, Any]] = []
    for quote_style, pattern in QUOTE_STYLE_PATTERNS:
        for match in pattern.finditer(text):
            quotes.append(
                {
                    "start": match.start(),
                    "end": match.end(),
                    "dialogue": match.group(1).strip(),
                    "speaker": None,
                    "method": "quote",
                    "quote_style": quote_style,
                    "confidence": 0.35,
                }
            )
    return deduplicate_by_position(quotes)


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
                q["confidence"] = 0.95
                break
        if q.get("speaker"):
            tracker.record(str(q["speaker"]))
            continue
        spacy_speaker = spacy_attr.attribute_unmatched(chapter_text, q["start"], q["end"])
        if spacy_speaker:
            q["speaker"] = spacy_speaker
            q["method"] = "spacy"
            q["confidence"] = 0.7
            tracker.record(spacy_speaker)
            continue
        predicted = tracker.predict_next()
        if predicted:
            q["speaker"] = predicted
            q["method"] = "alternation"
            q["confidence"] = 0.55
            tracker.record(predicted)
        else:
            q["speaker"] = None
            q["method"] = "unattributed"
            q["confidence"] = 0.2

    return quotes


def detect_dialogue_with_strategy(chapter_text: str, strategy: str = "auto") -> list[dict[str, Any]]:
    strategy_norm = normalize_dialogue_strategy(strategy)
    if strategy_norm == "regex_only":
        return extract_dialogue_regex(chapter_text)
    if strategy_norm == "quotes_only":
        return find_all_quotes(chapter_text)
    return detect_all_dialogue(chapter_text)
