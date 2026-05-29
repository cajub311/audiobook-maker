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


def _parse_voice_string(voice: str) -> tuple[str, str, float, str | None]:
    """Parse 'VoiceName|pitch=+2Hz|rate=-5%' into (voice_name, pitch_str, pitch_hz, rate_override).

    Lets callers embed pitch/rate into the voice field without changing the engine API.
    """
    parts = voice.split("|")
    voice_name = parts[0]
    pitch_str = "+0Hz"
    pitch_hz: float = 0.0
    rate_override: str | None = None
    for part in parts[1:]:
        if part.startswith("pitch="):
            pitch_str = part[6:]
            try:
                m = re.match(r"([+-]?\d+(?:\.\d+)?)", pitch_str)
                if m:
                    pitch_hz = float(m.group(1))
            except Exception:
                pitch_hz = 0.0
        elif part.startswith("rate="):
            rate_override = part[5:]
    return voice_name, pitch_str, pitch_hz, rate_override


# Abbreviations expanded before synthesis so TTS doesn't stumble on trailing dots.
_ABBREVS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bMr\.", re.I), "Mister"),
    (re.compile(r"\bMrs\.", re.I), "Missus"),
    (re.compile(r"\bMs\.", re.I), "Miss"),
    (re.compile(r"\bDr\.", re.I), "Doctor"),
    (re.compile(r"\bProf\.", re.I), "Professor"),
    (re.compile(r"\bSgt\.", re.I), "Sergeant"),
    (re.compile(r"\bCpl\.", re.I), "Corporal"),
    (re.compile(r"\bLt\.", re.I), "Lieutenant"),
    (re.compile(r"\bCapt\.", re.I), "Captain"),
    (re.compile(r"\bSt\.\s+(?=[A-Z])", re.I), "Saint "),
    (re.compile(r"\bvs\.", re.I), "versus"),
    (re.compile(r"\bJr\.", re.I), "Junior"),
    (re.compile(r"\bSr\.", re.I), "Senior"),
    (re.compile(r"\betc\.", re.I), "et cetera"),
]


def _clean_for_tts(text: str) -> str:
    """Normalize text so edge-tts speaks it naturally without reading markup as words."""
    # HTML entity decode before stripping tags
    text = (
        text.replace("&amp;", "&")
            .replace("&lt;", "<")
            .replace("&gt;", ">")
            .replace("&nbsp;", " ")
            .replace("&#39;", "'")
            .replace("&quot;", '"')
    )
    # Strip HTML / SSML / XML tags (after entity expansion so & doesn't confuse it)
    text = re.sub(r"<[^>]+>", "", text)
    # Expand abbreviations so trailing dots don't cause false sentence breaks
    for pattern, replacement in _ABBREVS:
        text = pattern.sub(replacement, text)
    # Em-dash → comma pause (reads as a natural beat rather than silence)
    text = re.sub(r"\s*—\s*", ", ", text)
    # Normalize ellipsis sequences → single Unicode ellipsis (edge-tts pauses on it)
    text = re.sub(r"\.\.\.+", "…", text)
    # Collapse repeated punctuation: !!! → !, ??? → ?
    text = re.sub(r"([!?]){2,}", r"\1", text)
    # ALL-CAPS words (4+ letters) → Title Case so TTS doesn't shout or spell them out
    text = re.sub(r"\b([A-Z]{4,})\b", lambda m: m.group(1).capitalize(), text)
    # Markdown formatting characters
    text = re.sub(r"[*_`~#\\]", "", text)
    # Collapse whitespace
    text = re.sub(r"\s+", " ", text).strip()
    return text


# --- Rich emotional SSML builder (ported from api/ssml-builder.js + parity extensions) ---
# Provides autoDetectEmotion, per-segment <mstts:express-as>, dialogue roles (role= attr),
# per-speaker emotionBias nudges, strategic breaks, emphasis, question/exclaim lifts.
# Makes Edge voices far more expressive and human in the desktop Gradio app (full parity with web).
# role and emotion_bias are fully optional + backward-compatible (None/"" = no change from prior behavior).

_MAX_SEGMENT_CHARS = 1200

_EMOTION_RULES: list[dict[str, Any]] = [
    {
        "name": "sad",
        "regex": re.compile(r"\b(sad|sorrow|grief|tears|heartbroken|weep|wept|mourn|mournful|despair|lonely|melancholy|tragically|devastated|funeral|loss|cried|grieving)\b", re.I),
        "style": "sad",
        "degreeFactor": 1.15,
    },
    {
        "name": "angry",
        "regex": re.compile(r"\b(angry|anger|furious|rage|raged|hate|hatred|shouted|snapped|growled|snarled|damn|bastard|hell|enraged|outraged|furiously|curse)\b", re.I),
        "style": "angry",
        "degreeFactor": 1.22,
    },
    {
        "name": "excited",
        "regex": re.compile(r"\b(excited|thrilled|amazing|wonderful|joy|ecstatic|fantastic|yay|hurrah|cheered|exhilarated|delighted|joyfully|magnificent)\b", re.I),
        "style": "cheerful",
        "degreeFactor": 1.28,
    },
    {
        "name": "whisper",
        "regex": re.compile(r"\b(whisper|whispered|softly|quietly|hushed|secret|murmur|muttered|under (his|her|their) breath|confided)\b", re.I),
        "style": "whisper",
        "degreeFactor": 0.78,
    },
    {
        "name": "fear",
        "regex": re.compile(r"\b(fear|terrified|scared|afraid|trembled|panic|panicked|horror|dread|shudder|terror)\b", re.I),
        "style": "terrified",
        "degreeFactor": 1.1,
    },
    {
        "name": "laugh",
        "regex": re.compile(r"\b(laugh|laughed|laughing|chuckle|chuckled|giggled|hilarious|funny|joked|roared with laughter)\b", re.I),
        "style": "cheerful",
        "degreeFactor": 0.9,
    },
    {
        "name": "gentle",
        "regex": re.compile(r"\b(gently|soft|warmly|tender|caressed|smiled softly|kindly|lovingly)\b", re.I),
        "style": "empathetic",
        "degreeFactor": 0.95,
    },
]


def _detect_emotion(text: str, global_expressiveness: float) -> Optional[dict[str, str]]:
    if not text or global_expressiveness < 0.2:
        return None
    best: Optional[dict[str, Any]] = None
    best_score = 0
    for rule in _EMOTION_RULES:
        matches = rule["regex"].findall(text)
        score = len(matches) if matches else 0
        if score > best_score:
            best_score = score
            best = rule
    if not best:
        return None
    scaled = best["degreeFactor"] * (0.6 + global_expressiveness * 0.85)
    deg = max(0.4, min(1.9, scaled))
    return {"style": best["style"], "degree": f"{deg:.1f}", "name": best["name"]}


def _xml_escape(text: str) -> str:
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )


def _clamp_rate(speed: float) -> float:
    if not isinstance(speed, (int, float)):
        return 0.0
    try:
        if speed != speed:  # NaN
            return 0.0
    except Exception:
        return 0.0
    return max(-0.5, min(0.5, float(speed)))


def _format_rate_as_percent(rate: float) -> str:
    pct = int(round(rate * 100))
    if pct == 0:
        return "+0%"
    return f"+{pct}%" if pct > 0 else f"{pct}%"


def _format_pitch(pitch: float) -> str:
    if not pitch or pitch == 0:
        return "+0Hz"
    sign = "+" if pitch > 0 else ""
    if abs(pitch - round(pitch)) < 0.1:
        return f"{sign}{int(pitch)}Hz"
    return f"{sign}{pitch}Hz"


def _format_volume(volume: float) -> str:
    if not volume or volume == 0:
        return "+0%"
    sign = "+" if volume > 0 else ""
    return f"{sign}{int(round(volume))}%"


def _build_segment_ssml(seg: dict[str, Any], opts: dict[str, Any]) -> str:
    rate_pct = opts.get("rate_pct", "+0%")
    pitch_str = opts.get("pitch_str", "+0Hz")
    vol_str = opts.get("vol_str", "+0%")
    expressiveness = opts.get("expressiveness", 0.68)
    role_hint = opts.get("role_hint")
    dialogue_hint = opts.get("dialogue_hint", False)

    content = _xml_escape(seg["text"])

    # Word-level emphasis on powerful emotional words
    content = re.sub(
        r"\b(never|always|only|just|really|so|too|completely|utterly|now|no|desperately|run|time)\b",
        r'<emphasis level="moderate">\1</emphasis>',
        content,
        flags=re.I,
    )

    # Natural pauses
    content = re.sub(r"([,;:])\s+", r"\1 <break time=\"180ms\"/> ", content)
    content = re.sub(r"([.!?])\s+(?=[A-Z\"'])", r"\1 <break time=\"420ms\"/> ", content)
    content = re.sub(r"([.!?])(?=\s*$)", r"\1 <break time=\"420ms\"/> ", content)
    content = re.sub(r"—\s*", "— <break time=\"300ms\"/> ", content)
    content = re.sub(r"--\s*", "— <break time=\"280ms\"/> ", content)

    seg_content = f'<prosody rate="{rate_pct}" pitch="{pitch_str}" volume="{vol_str}">{content}</prosody>'

    # Auto emotion per segment (the big win for natural voices)
    emo = _detect_emotion(seg["text"], expressiveness)
    if emo:
        role = (seg.get("is_dialogue") or dialogue_hint) and (role_hint or "YoungAdultFemale")
        role_attr = f' role="{role}"' if role else ""
        seg_content = f'<mstts:express-as style="{emo["style"]}" styledegree="{emo["degree"]}"{role_attr}>{seg_content}</mstts:express-as>'

    # [tags] from Voice Direction
    seg_content = re.sub(
        r"\[(sad|angry|whisper|terrified|cheerful|empathetic|sarcastic|reflective|urgent|gentle)\]",
        lambda m: f'<mstts:express-as style="{m.group(1).lower()}" styledegree="1.15"></mstts:express-as>',
        seg_content,
        flags=re.I,
    )
    return seg_content


def text_to_rich_ssml(text: str, options: dict[str, Any] | None = None) -> str:
    opts = options or {}
    rate = opts.get("rate", 0.0)
    pitch = opts.get("pitch", 0.0)
    volume = opts.get("volume", 0.0)
    style = (opts.get("style") or "natural").lower()
    expressiveness = float(opts.get("expressiveness", 0.68))
    is_dialogue = bool(opts.get("is_dialogue", False))
    role = opts.get("role")
    emotion_bias = opts.get("emotion_bias") or opts.get("emotionBias")
    voice_direction = opts.get("voice_direction") or opts.get("voiceDirection")

    # Auto emotion detection (parity with web)
    auto = _auto_detect_emotion(text)
    if style == "auto" or (expressiveness > 0.5 and auto["expressiveness_boost"] > 0):
        style = auto["suggested_style"]
        expressiveness = min(0.95, expressiveness + auto["expressiveness_boost"])

    # Voice Direction nudges
    if voice_direction:
        dir_lower = str(voice_direction).lower()
        boosts = {
            "whisper": 0.10, "whispering": 0.10, "intense": 0.12, "dramatic": 0.09,
            "angry": 0.13, "furious": 0.12, "sad": 0.09, "excited": 0.11,
            "ecstatic": 0.13, "gentle": 0.07, "terrified": 0.10, "fear": 0.09,
            "cheerful": 0.10, "empathetic": 0.08, "sarcastic": 0.06,
            "reflective": 0.05, "urgent": 0.07, "calm": 0.03,
        }
        for key, boost in boosts.items():
            if key in dir_lower or f"[{key}" in dir_lower:
                expressiveness = min(0.96, expressiveness + boost)
                if style in ("auto", "natural") and key in ("whisper", "angry", "sad", "cheerful", "empathetic", "terrified", "intense", "dramatic"):
                    style = "whisper" if key == "whisper" else key

    # Per-speaker emotion bias (from UI grid)
    if emotion_bias:
        b = str(emotion_bias).lower().strip()
        bias_boost = {"cheerful": 0.12, "excited": 0.15, "dramatic": 0.10, "intense": 0.14, "calm": 0.02, "empathetic": 0.06, "sad": 0.05, "whispering": 0.03, "sarcastic": 0.04}
        if b in bias_boost:
            expressiveness = min(0.96, expressiveness + bias_boost[b])
        if style in ("auto", "natural") and b in bias_boost:
            style = b

    cleaned = _clean_for_tts(text)
    if not cleaned:
        return '<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xmlns:mstts="http://www.w3.org/2001/mstts" xml:lang="en-US"><prosody rate="+0%" pitch="+0Hz" volume="+0%">...</prosody></speak>'

    rate_pct = _format_rate_as_percent(_clamp_rate(rate))
    pitch_str = _format_pitch(pitch)
    vol_str = _format_volume(volume)

    # Simple segmentation for demo (full version uses the JS segmentText logic)
    segments = [{"text": cleaned, "is_dialogue": is_dialogue}]

    has_dialogue = any(s.get("is_dialogue") for s in segments)
    express_style = None
    express_map = {
        "dramatic": ("narration-professional", "cheerful"),
        "conversational": ("friendly", "friendly"),
        "gentle": ("empathetic", "empathetic"),
        "intense": ("angry", "terrified"),
        "excited": ("cheerful", "excited"),
        "sad": ("sad", "empathetic"),
        "calm": ("calm", "gentle"),
    }
    if style in express_map and expressiveness >= 0.35:
        base, dlg = express_map[style]
        express_style = dlg if has_dialogue else base

    inner_parts = []
    for seg in segments:
        inner_parts.append(_build_segment_ssml(seg, {
            "rate_pct": rate_pct,
            "pitch_str": pitch_str,
            "vol_str": vol_str,
            "expressiveness": expressiveness,
            "role_hint": role,
            "dialogue_hint": is_dialogue,
        }))
    inner = " ".join(inner_parts)

    has_local = "mstts:express-as" in inner
    if express_style and expressiveness > 0.30 and (not has_local or expressiveness > 0.78):
        role_attr = f' role="{role}"' if role else ""
        deg = max(0.6, min(1.9, expressiveness * 1.6))
        inner = f'<mstts:express-as style="{express_style}" styledegree="{deg:.1f}"{role_attr}>{inner}</mstts:express-as>'

    return f'<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xmlns:mstts="http://www.w3.org/2001/mstts" xml:lang="en-US">{inner}</speak>'


def _auto_detect_emotion(text: str) -> dict[str, Any]:
    t = str(text or "").lower()
    style = "natural"
    boost = 0.0
    cues = {
        "ecstatic": ["amazing", "incredible", "best ever", "fantastic", "ecstatic", "!"],
        "excited": ["excited", "can't wait", "wow", "suddenly", "!"],
        "sarcastic": ["sure", "yeah right", "of course", "as if"],
        "whispering": ["whisper", "quietly", "don't tell", "secret"],
        "sad": ["sad", "sorry", "cried", "whispered", "trembling", "lost"],
        "angry": ["angry", "furious", "shouted", "how dare", "never"],
        "gentle": ["softly", "gently", "warm", "calm", "whispered"],
        "intense": ["suddenly", "everything changed", "desperately", "now!"],
    }
    for s, words in cues.items():
        if any(w in t for w in words):
            style = s
            boost = 0.15
            break
    exclam = t.count("!")
    q = t.count("?")
    if exclam > 1:
        style = "excited"
        boost += 0.1
    if q > 0 and style == "natural":
        style = "conversational"
    return {"suggested_style": style, "expressiveness_boost": min(0.3, boost)}


def text_to_basic_ssml(text: str, rate: float = 0.0, pitch: float = 0.0, volume: float = 0.0) -> str:
    r = _format_rate_as_percent(_clamp_rate(rate))
    p = _format_pitch(pitch)
    v = _format_volume(volume)
    return f'<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xmlns:mstts="http://www.w3.org/2001/mstts" xml:lang="en-US"><prosody rate="{r}" pitch="{p}" volume="{v}">{_xml_escape(_clean_for_tts(text))}</prosody></speak>'


# Public API for the rest of the Python app (parity with the Node side)
__all__ = ["text_to_rich_ssml", "text_to_basic_ssml", "_clean_for_tts"]

# Also expose the internal helpers so the big v7 monolith and tests can import them directly
textToRichSSML = text_to_rich_ssml
textToBasicSSML = text_to_basic_ssml
cleanForTTS = _clean_for_tts
