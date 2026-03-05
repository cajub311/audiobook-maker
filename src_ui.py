"""
src_ui.py — Audiobook Creator V7
Gradio UI (5 tabs) + FastAPI REST API + App entry point.

This module is designed to be used standalone or merged into a single-file app.
Handler functions that depend on the full pipeline (src_manifest.py,
src_tts_audio.py, etc.) are implemented as stubs that print diagnostic
messages until those modules are imported.
"""

from __future__ import annotations

import json
import os
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import gradio as gr
import uvicorn
from fastapi import BackgroundTasks, FastAPI, HTTPException
from pydantic import BaseModel

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SETTINGS_FILE = Path("settings.json")

ENGINES: List[str] = [
    "edge-tts (Cloud, Free)",
    "Kokoro (Offline, CPU)",
]

EDGE_TTS_VOICES: List[str] = [
    "en-US-GuyNeural",
    "en-US-JennyNeural",
    "en-US-AriaNeural",
    "en-US-DavisNeural",
    "en-US-TonyNeural",
    "en-US-NancyNeural",
    "en-GB-RyanNeural",
    "en-GB-SoniaNeural",
    "en-GB-LibbyNeural",
    "en-AU-WilliamNeural",
    "en-AU-NatashaNeural",
    "en-CA-ClaraNeural",
    "en-IE-ConnorNeural",
    "en-IN-NeerjaNeural",
    "en-IN-PrabhatNeural",
]

KOKORO_VOICES: List[str] = [
    "af",
    "af_bella",
    "af_sarah",
    "am_adam",
    "am_michael",
    "bf_emma",
    "bf_isabella",
    "bm_george",
    "bm_lewis",
]

PRONUNCIATION_PRESETS: Dict[str, List[List[str]]] = {
    "None": [],
    "Demon Cycle": [
        ["Arlen", "AR-len"],
        ["Leesha", "LEE-sha"],
        ["Rojer", "ROH-jer"],
        ["Inevera", "in-EV-er-ah"],
        ["Jardir", "jar-DEER"],
        ["Renna", "REN-ah"],
        ["Briar", "BRY-ar"],
    ],
    "Wheel of Time": [
        ["Nynaeve", "NYE-neev"],
        ["Egwene", "EH-gween"],
        ["Siuan", "SWAHN"],
        ["Moiraine", "mwah-RAIN"],
        ["al'Thor", "al-THOR"],
        ["Aes Sedai", "AYS seh-DYE"],
        ["Lan", "LAHN"],
    ],
    "Dune": [
        ["Atreides", "ah-TRAY-deez"],
        ["Bene Gesserit", "BEN-ee JESS-er-it"],
        ["Kwisatz Haderach", "KWEE-satz HAD-er-ak"],
        ["Mentats", "MEN-tats"],
        ["Sardaukar", "SAR-dow-kar"],
        ["Muad'Dib", "moo-AHD-dib"],
        ["Fremen", "FREE-men"],
    ],
}

EXPORT_PRESETS: List[str] = [
    "Audiobook Standard (M4B, -19 LUFS)",
    "Podcast Quality (MP3, -16 LUFS)",
    "High Quality (FLAC, -19 LUFS)",
]

# ---------------------------------------------------------------------------
# Settings Persistence
# ---------------------------------------------------------------------------

DEFAULT_SETTINGS: Dict[str, Any] = {
    "engine": "edge-tts (Cloud, Free)",
    "narrator_voice": "en-US-GuyNeural",
    "dialogue_voice": "en-US-JennyNeural",
    "speed": 1.0,
    "output_format": "M4B (Chaptered)",
    "normalize": True,
    "export_preset": "Audiobook Standard (M4B, -19 LUFS)",
    "bg_music_volume": 20,
    "theme_label": "☀️ Light Mode",
}


def load_settings() -> Dict[str, Any]:
    """Load persisted settings from disk, merging with defaults for missing keys."""
    if SETTINGS_FILE.exists():
        try:
            with open(SETTINGS_FILE) as fh:
                data = json.load(fh)
            return {**DEFAULT_SETTINGS, **data}
        except Exception as exc:
            print(f"[Settings] Could not load {SETTINGS_FILE}: {exc}")
    return DEFAULT_SETTINGS.copy()


def save_settings(settings: Dict[str, Any]) -> None:
    """Persist settings dictionary to disk as JSON."""
    try:
        with open(SETTINGS_FILE, "w") as fh:
            json.dump(settings, fh, indent=2)
    except Exception as exc:
        print(f"[Settings] Failed to save: {exc}")


# ---------------------------------------------------------------------------
# In-Memory Job Store  (replace with a DB or manifest layer in production)
# ---------------------------------------------------------------------------

_jobs: Dict[str, Dict[str, Any]] = {}
_stats: Dict[str, Any] = {
    "total_books": 0,
    "total_seconds": 0,
    "cache_hits": 0,
    "cache_size_bytes": 0,
}

# ---------------------------------------------------------------------------
# Handler Stubs
# ---------------------------------------------------------------------------


def parse_book_handler(
    file_obj: Optional[Any],
    url: str,
    text: str,
    engine: str,
) -> Tuple[List[List[Any]], str, str, str]:
    """
    Parse the supplied input source and extract chapters with metadata.

    Accepts a file upload, a URL, or raw pasted text — whichever is non-empty.
    Returns a tuple of:
        chapter_rows  — rows ready for the chapter Dataframe
        analysis_md   — markdown block with book statistics
        time_estimate — human-readable estimate of generation time
        log_message   — single-line status string for the log widget
    """
    print(
        f"[parse_book_handler] engine={engine!r}  "
        f"url={url!r}  has_file={file_obj is not None}  has_text={bool(text.strip())}"
    )

    if file_obj is None and not url.strip() and not text.strip():
        return (
            [],
            "*No input provided — upload a file, paste a URL, or enter text above.*",
            "",
            "⚠️  Please provide a file, URL, or text before parsing.",
        )

    # ── Stub chapter data ────────────────────────────────────────────────────
    chapter_rows: List[List[Any]] = [
        [1, "Prologue", 12, 3, "✅"],
        [2, "Chapter 1 — The Beginning", 45, 7, "❌"],
        [3, "Chapter 2 — The Journey", 38, 5, "❌"],
        [4, "Chapter 3 — The Challenge", 52, 9, "✅"],
        [5, "Chapter 4 — The Resolution", 41, 6, "❌"],
        [6, "Epilogue", 8, 2, "✅"],
    ]

    total_segments = sum(r[2] for r in chapter_rows)
    total_chars_detected = sum(r[3] for r in chapter_rows)

    analysis_md = (
        "### 📊 Book Analysis\n\n"
        "| Metric | Value |\n"
        "|--------|-------|\n"
        "| **Word Count** | ~42,000 |\n"
        "| **Estimated Audio Duration** | ~3 h 15 m |\n"
        "| **Chapters Detected** | 6 |\n"
        f"| **Total Segments** | {total_segments} |\n"
        f"| **Characters Detected** | {total_chars_detected} |\n\n"
        "**Top Characters:** Arlen (187), Leesha (142), Rojer (98), "
        "Jardir (76), Inevera (61)\n\n"
        "> Analysis complete. Review and adjust chapters below before generating."
    )

    # Rough speed heuristic: Edge-TTS is faster due to cloud parallelism
    secs_per_segment = 0.8 if "edge" in engine.lower() else 1.4
    est_minutes = max(1, int(total_segments * secs_per_segment / 60))
    time_estimate = (
        f"⏱️  **Estimated generation time:** ~{est_minutes} min  "
        f"with *{engine}*"
    )

    return (
        chapter_rows,
        analysis_md,
        time_estimate,
        "✅  Parsing complete — 6 chapters detected.",
    )


def get_voices_for_engine(engine: str) -> List[str]:
    """Return the ordered list of voice identifiers available for *engine*."""
    return KOKORO_VOICES if "Kokoro" in engine else EDGE_TTS_VOICES


def preview_voice_handler(voice: str, engine: str) -> Optional[str]:
    """
    Generate a short TTS preview clip for *voice* using *engine*.

    Returns the filesystem path to the generated WAV/MP3 file, or *None*
    when the TTS engine is not yet available (stub mode).
    """
    print(f"[preview_voice_handler] voice={voice!r}  engine={engine!r}")
    # Wire up: call EdgeTTSEngine or KokoroEngine to generate ~5 s of audio
    # and return the path, e.g.:
    #   from src_tts_audio import EdgeTTSEngine
    #   ...
    return None


def generate_handler(
    chapter_data: List[List[Any]],
    engine: str,
    narrator_voice: str,
    dialogue_voice: str,
    character_voices: List[List[Any]],
    pronunciation_overrides: List[List[str]],
    speed: float,
    output_format: str,
    normalize: bool,
    export_preset: str,
    bg_music_path: Optional[str],
    bg_music_volume: float,
    cancel_state: bool,
    progress: gr.Progress = gr.Progress(),
) -> Tuple[str, str, List[List[Any]], Optional[str]]:
    """
    Drive the full audiobook generation pipeline for all chapters.

    Returns a tuple of:
        log_text        — accumulated log string
        status_md       — final status markdown line
        chapter_rows    — updated per-chapter progress rows
        output_path     — path to the assembled audiobook (or None in stub mode)
    """
    print(
        f"[generate_handler] engine={engine!r}  format={output_format!r}  "
        f"narrator={narrator_voice!r}  dialogue={dialogue_voice!r}  "
        f"speed={speed}  normalize={normalize}  preset={export_preset!r}"
    )

    log_lines: List[str] = [
        f"[{time.strftime('%H:%M:%S')}] Generation started — {len(chapter_data or [])} chapters",
        f"[{time.strftime('%H:%M:%S')}] Engine: {engine}  |  Speed: {speed}×",
        f"[{time.strftime('%H:%M:%S')}] Format: {output_format}  |  Preset: {export_preset}",
    ]
    chapter_rows: List[List[Any]] = []

    chapters = chapter_data or []
    total = max(len(chapters), 1)

    for idx, row in enumerate(chapters):
        if cancel_state:
            log_lines.append(f"[{time.strftime('%H:%M:%S')}] ⛔  Cancelled at chapter {idx + 1}.")
            break

        title = row[1] if len(row) > 1 else f"Chapter {idx + 1}"
        segments = int(row[2]) if len(row) > 2 else 0

        progress((idx + 0.5) / total, desc=f'Generating "{title}"…')
        time.sleep(0.15)  # stub delay — remove when pipeline is wired

        log_lines.append(
            f"[{time.strftime('%H:%M:%S')}] ✅  {title}  ({segments} segments)"
        )
        chapter_rows.append([title, "✅ Done", segments, "—"])

    if not cancel_state:
        progress(1.0, desc="Assembling final audiobook…")
        log_lines.append(
            f"[{time.strftime('%H:%M:%S')}] Assembling output — "
            f"wire src_tts_audio.encode_to_m4b() for real output."
        )
        status_md = "✅  **Generation complete** *(stub run — no audio produced yet)*"
        _stats["total_books"] += 1
    else:
        status_md = "⛔  **Generation stopped by user.**"

    return "\n".join(log_lines), status_md, chapter_rows, None


def load_pronunciation_preset(preset_name: str) -> List[List[str]]:
    """Return the pronunciation table rows for the named preset."""
    return PRONUNCIATION_PRESETS.get(preset_name, [])


def add_bookmark_handler(
    current_position: str,
    bookmarks: Optional[List[List[str]]],
) -> List[List[str]]:
    """Append a timestamp bookmark at *current_position* to the bookmarks list."""
    ts = time.strftime("%H:%M:%S")
    position = current_position or "0:00:00"
    updated = list(bookmarks or [])
    updated.append([ts, position, "Chapter bookmark"])
    return updated


def get_cache_stats() -> Dict[str, Any]:
    """
    Return cache statistics from disk.

    Stub: reads the tts_cache directory size.  Wire up AudioCache from
    src_manifest.py for hit-rate tracking.
    """
    cache_dir = Path("tts_cache")
    size_bytes = sum(f.stat().st_size for f in cache_dir.rglob("*") if f.is_file()) \
        if cache_dir.exists() else 0
    size_mb = size_bytes / (1024 * 1024)
    return {"size_mb": round(size_mb, 1), "hits": _stats["cache_hits"]}


# ---------------------------------------------------------------------------
# UI Builder
# ---------------------------------------------------------------------------

_CUSTOM_CSS = """
/* ── Header ──────────────────────────────────────────────────────────────── */
.ac7-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0.4rem 0.75rem;
    border-bottom: 1px solid var(--border-color-primary);
    margin-bottom: 0.25rem;
    gap: 0.5rem;
}
.ac7-title {
    font-size: 1.45rem;
    font-weight: 700;
    letter-spacing: -0.02em;
    flex: 1;
}

/* ── Stat cards ─────────────────────────────────────────────────────────── */
.stat-card {
    background: var(--background-fill-secondary);
    border-radius: 10px;
    padding: 0.85rem 1rem;
    border: 1px solid var(--border-color-primary);
    text-align: center;
}

/* ── Keyboard shortcut chips ─────────────────────────────────────────────── */
.kbd {
    display: inline-block;
    font-family: ui-monospace, monospace;
    background: var(--background-fill-secondary);
    padding: 1px 7px;
    border-radius: 5px;
    border: 1px solid var(--border-color-primary);
    font-size: 0.82em;
    line-height: 1.6;
}

/* ── Subtle info bar ─────────────────────────────────────────────────────── */
.info-banner {
    background: var(--background-fill-secondary);
    border-left: 3px solid var(--primary-500);
    padding: 0.5rem 0.75rem;
    border-radius: 0 6px 6px 0;
    font-size: 0.9em;
    margin-bottom: 0.5rem;
}
"""


def _build_theme() -> gr.themes.Base:
    """Construct the shared Gradio theme instance."""
    return gr.themes.Soft(
        primary_hue="violet",
        secondary_hue="blue",
        neutral_hue="slate",
        font=[gr.themes.GoogleFont("Inter"), "ui-sans-serif", "sans-serif"],
    ).set(
        button_primary_background_fill="*primary_500",
        button_primary_background_fill_hover="*primary_600",
        button_primary_text_color="white",
    )


def build_ui() -> gr.Blocks:
    """
    Construct and return the full Gradio Blocks application.

    The returned Blocks object can be mounted into an existing ASGI app or
    launched directly via ``app.launch(theme=_build_theme(), css=_CUSTOM_CSS)``.
    """
    settings = load_settings()

    with gr.Blocks(
        title="Audiobook Creator V7",
        analytics_enabled=False,
    ) as app:

        # ── Shared state ─────────────────────────────────────────────────────
        cancel_state = gr.State(False)
        current_job_id = gr.State("")
        parsed_chapters = gr.State([])
        current_position_state = gr.State("0:00:00")

        # ── Header ───────────────────────────────────────────────────────────
        with gr.Row(elem_classes="ac7-header"):
            gr.Markdown(
                "## 🎙️ Audiobook Creator V7",
                elem_classes="ac7-title",
            )
            theme_toggle_btn = gr.Button(
                value=settings.get("theme_label", "☀️ Light Mode"),
                size="sm",
                variant="secondary",
                min_width=130,
            )

        # ── Tabs ─────────────────────────────────────────────────────────────
        with gr.Tabs():

            # ================================================================
            # TAB 1 — 📖 INPUT
            # ================================================================
            with gr.TabItem("📖 Input"):
                gr.Markdown(
                    "### Import Your Book\n"
                    "Upload an **EPUB, PDF, or TXT** file, paste a URL "
                    "(e.g. Project Gutenberg), or type/paste text directly. "
                    "Only one source is required."
                )

                with gr.Row():
                    with gr.Column(scale=1):
                        input_file = gr.File(
                            label="Upload File  (EPUB / PDF / TXT)",
                            file_types=[".epub", ".pdf", ".txt"],
                            interactive=True,
                        )
                        input_url = gr.Textbox(
                            label="Book URL",
                            placeholder="https://www.gutenberg.org/ebooks/…",
                            info="Paste a Project Gutenberg or similar publicly accessible URL.",
                        )

                    with gr.Column(scale=1):
                        input_text = gr.Textbox(
                            label="Paste Text Directly",
                            placeholder=(
                                "Chapter 1\n\nIt was a dark and stormy night…\n\n"
                                "Chapter 2\n\nThe morning brought no relief…"
                            ),
                            lines=10,
                            max_lines=24,
                            info="Use blank lines between chapters for automatic detection.",
                        )

                parse_btn = gr.Button(
                    "📋  Parse & Detect Chapters",
                    variant="primary",
                    size="lg",
                )

                with gr.Accordion("📊 Book Analysis", open=False) as analysis_accordion:
                    analysis_stats_md = gr.Markdown(
                        "*Parse a book above to see word count, character list, "
                        "and estimated audio duration.*"
                    )

                gr.Markdown("### Detected Chapters")
                gr.Markdown(
                    "*Chapters and segments are listed below after parsing. "
                    "The **Cached** column shows which chapters have pre-built audio "
                    "in the TTS cache and can be skipped during generation.*",
                    elem_classes="info-banner",
                )
                chapter_list_df = gr.Dataframe(
                    headers=["#", "Chapter Title", "Segments", "Characters Found", "Cached"],
                    datatype=["number", "str", "number", "number", "str"],
                    interactive=False,
                    wrap=True,
                    label="Chapters",
                )
                time_estimate_md = gr.Markdown("")

            # ================================================================
            # TAB 2 — 🎤 VOICES
            # ================================================================
            with gr.TabItem("🎤 Voices"):
                gr.Markdown(
                    "### Voice Configuration\n"
                    "Choose your TTS engine and assign voices to the narrator, "
                    "default dialogue speaker, and any auto-detected characters."
                )

                engine_radio = gr.Radio(
                    choices=ENGINES,
                    value=settings["engine"],
                    label="TTS Engine",
                    info=(
                        "**Edge-TTS** streams from Microsoft's cloud servers — "
                        "fast and natural-sounding, requires internet.  "
                        "**Kokoro** runs fully offline on your CPU after a one-time model download."
                    ),
                )

                # ── Narrator & Dialogue voice pickers ────────────────────────
                with gr.Row():
                    with gr.Column():
                        gr.Markdown("#### 🎙️ Narrator Voice")
                        _initial_voices = get_voices_for_engine(settings["engine"])
                        _narrator_default = (
                            settings["narrator_voice"]
                            if settings["narrator_voice"] in _initial_voices
                            else _initial_voices[0]
                        )
                        narrator_voice_dd = gr.Dropdown(
                            choices=_initial_voices,
                            value=_narrator_default,
                            label="Narrator Voice",
                            interactive=True,
                            info="Used for all non-dialogue narration text.",
                        )
                        narrator_preview_btn = gr.Button("▶  Preview Narrator", size="sm")
                        narrator_preview_audio = gr.Audio(
                            label="Narrator Preview",
                            type="filepath",
                            interactive=False,
                            buttons=[],
                        )

                    with gr.Column():
                        gr.Markdown("#### 💬 Default Dialogue Voice")
                        _dialogue_default = (
                            settings["dialogue_voice"]
                            if settings["dialogue_voice"] in _initial_voices
                            else (_initial_voices[1] if len(_initial_voices) > 1 else _initial_voices[0])
                        )
                        dialogue_voice_dd = gr.Dropdown(
                            choices=_initial_voices,
                            value=_dialogue_default,
                            label="Default Dialogue Voice",
                            interactive=True,
                            info=(
                                "Used for unattributed speech or characters without "
                                "an explicit voice assignment below."
                            ),
                        )
                        dialogue_preview_btn = gr.Button("▶  Preview Dialogue", size="sm")
                        dialogue_preview_audio = gr.Audio(
                            label="Dialogue Preview",
                            type="filepath",
                            interactive=False,
                            buttons=[],
                        )

                # ── Character voice assignments ───────────────────────────────
                gr.Markdown("#### 👥 Character Voice Assignments")
                gr.Markdown(
                    "Characters are auto-detected from the text after parsing. "
                    "Click any cell in the **Assigned Voice** or **Method** columns "
                    "to override the default assignment.",
                    elem_classes="info-banner",
                )
                character_voices_df = gr.Dataframe(
                    headers=["Character", "Detected Occurrences", "Assigned Voice", "Method"],
                    datatype=["str", "number", "str", "str"],
                    interactive=True,
                    wrap=True,
                    row_count=(5, "dynamic"),
                    column_count=(4, "fixed"),
                    label="Character Voice Assignments",
                )

                # ── Pronunciation overrides ───────────────────────────────────
                with gr.Accordion("🔤 Pronunciation Overrides", open=False):
                    gr.Markdown(
                        "Teach the engine how to pronounce unusual words, proper "
                        "nouns, or invented names.  Add your own rows or load a "
                        "preset for popular fantasy series."
                    )
                    with gr.Row():
                        preset_dd = gr.Dropdown(
                            choices=list(PRONUNCIATION_PRESETS.keys()),
                            value="None",
                            label="Load Series Preset",
                            scale=3,
                        )
                        load_preset_btn = gr.Button("Load Preset", size="sm", scale=1)
                    pronunciation_df = gr.Dataframe(
                        headers=["Word", "Sounds Like"],
                        datatype=["str", "str"],
                        interactive=True,
                        row_count=(5, "dynamic"),
                        column_count=(2, "fixed"),
                        label="Pronunciation Overrides",
                    )

                # ── Speed & Background music ──────────────────────────────────
                with gr.Row():
                    speed_slider = gr.Slider(
                        minimum=0.8,
                        maximum=1.3,
                        value=settings["speed"],
                        step=0.05,
                        label="Narration Speed",
                        info="1.0 = normal pace.  0.9 works well for dense prose.",
                        scale=2,
                    )

                with gr.Accordion("🎵 Background Music  (optional)", open=False):
                    gr.Markdown(
                        "Upload an ambient music file to play softly behind the narration. "
                        "The file will be looped to match the total audiobook duration."
                    )
                    bg_music_file = gr.File(
                        label="Background Music File  (MP3 / WAV / OGG / FLAC)",
                        file_types=[".mp3", ".wav", ".ogg", ".flac"],
                        interactive=True,
                    )
                    bg_volume_slider = gr.Slider(
                        minimum=0,
                        maximum=100,
                        value=settings["bg_music_volume"],
                        step=5,
                        label="Background Music Volume  (%)",
                        info="Volume relative to the narration track.  10–20 % is a good starting point.",
                    )

            # ================================================================
            # TAB 3 — ⚡ GENERATE
            # ================================================================
            with gr.TabItem("⚡ Generate"):
                gr.Markdown(
                    "### Generate Audiobook\n"
                    "All voice and engine settings from the **Voices** tab are "
                    "applied automatically.  Parse your book first to unlock the "
                    "time estimate and per-chapter progress."
                )

                # ── Action buttons ────────────────────────────────────────────
                with gr.Row():
                    generate_btn = gr.Button(
                        "🚀  Generate Audiobook",
                        variant="primary",
                        size="lg",
                        scale=3,
                    )
                    stop_btn = gr.Button(
                        "⛔  Stop",
                        variant="stop",
                        size="lg",
                        scale=1,
                    )
                    resume_btn = gr.Button(
                        "↩️  Resume",
                        size="lg",
                        scale=1,
                    )

                # ── Output format & normalization ─────────────────────────────
                with gr.Row():
                    output_format_radio = gr.Radio(
                        choices=["M4B (Chaptered)", "MP3 (Simple)"],
                        value=settings["output_format"],
                        label="Output Format",
                        info=(
                            "**M4B** embeds chapter markers for compatible players.  "
                            "**MP3** is universally compatible."
                        ),
                    )
                    normalize_chk = gr.Checkbox(
                        value=settings["normalize"],
                        label="Normalize Audio Levels",
                        info="Recommended — applies loudness normalisation for consistent playback volume.",
                    )

                export_preset_radio = gr.Radio(
                    choices=EXPORT_PRESETS,
                    value=settings["export_preset"],
                    label="Export Preset",
                    info=(
                        "Presets override the Output Format and set the loudness target. "
                        "**Audiobook Standard** matches Audible's -19 LUFS spec."
                    ),
                )

                time_estimate_gen_md = gr.Markdown(
                    "*Parse a book on the **Input** tab to see a generation time estimate.*"
                )

                # ── Progress ──────────────────────────────────────────────────
                gr.Markdown("#### Generation Progress")
                status_md = gr.Markdown("*Ready to generate.*")

                chapter_progress_df = gr.Dataframe(
                    headers=["Chapter", "Status", "Segments Done", "Duration"],
                    datatype=["str", "str", "number", "str"],
                    interactive=False,
                    wrap=True,
                    label="Per-Chapter Progress",
                )

                gen_log_tb = gr.Textbox(
                    interactive=False,
                    lines=8,
                    label="Generation Log",
                    placeholder="Generation output will appear here…",
                )

                # ── Keyboard shortcuts reference ──────────────────────────────
                with gr.Accordion("⌨️  Keyboard Shortcuts Reference", open=False):
                    gr.Markdown(
                        "| Action | Shortcut |\n"
                        "|--------|----------|\n"
                        "| **Start generation** | Click **🚀 Generate Audiobook** |\n"
                        "| **Stop generation** | Click **⛔ Stop** |\n"
                        "| **Parse book** | Click **📋 Parse & Detect Chapters** on the Input tab |\n"
                        "| **Preview voice** | Click **▶ Preview** on the Voices tab |\n\n"
                        "> Full keyboard shortcuts will be enabled in a future release.\n\n"
                        "**Pro tips:**\n"
                        "- Use the TTS cache to skip unchanged chapters on re-runs.\n"
                        "- Resume interrupted jobs with **↩️ Resume** — the manifest "
                        "  tracks exactly which segments have been completed.\n"
                        "- Pronunciation overrides apply globally across all chapters."
                    )

            # ================================================================
            # TAB 4 — 🎧 PLAYER & EXPORT
            # ================================================================
            with gr.TabItem("🎧 Player & Export"):
                gr.Markdown(
                    "### Playback & Export\n"
                    "Listen to the generated audiobook, jump between chapters, "
                    "add bookmarks, and download the final file."
                )

                # ── Audio player ──────────────────────────────────────────────
                output_audio_player = gr.Audio(
                    label="Audiobook Player",
                    type="filepath",
                    interactive=False,
                    buttons=["download"],
                )

                chapter_nav_dd = gr.Dropdown(
                    choices=["— Select a chapter to jump to —"],
                    value="— Select a chapter to jump to —",
                    label="Jump to Chapter",
                    interactive=True,
                    info="Navigate directly to the start of any chapter.",
                )

                # ── Bookmarks ─────────────────────────────────────────────────
                gr.Markdown("#### 🔖 Bookmarks")
                with gr.Row():
                    add_bookmark_btn = gr.Button("🔖  Add Bookmark", size="sm")
                    gr.Markdown(
                        "*Click to bookmark the current playback position.*",
                        elem_classes="info-banner",
                    )

                bookmarks_df = gr.Dataframe(
                    headers=["Time Added", "Position", "Note"],
                    datatype=["str", "str", "str"],
                    interactive=True,
                    row_count=(3, "dynamic"),
                    column_count=(3, "fixed"),
                    label="Bookmarks",
                )

                # ── Download ──────────────────────────────────────────────────
                gr.Markdown("#### 💾 Download")
                download_file = gr.File(
                    label="Download Audiobook",
                    interactive=False,
                )

                # ── Export statistics ─────────────────────────────────────────
                with gr.Accordion("📈 Export Statistics", open=True):
                    export_stats_md = gr.Markdown(
                        "| Metric | Value |\n"
                        "|--------|-------|\n"
                        "| **Total Duration** | — |\n"
                        "| **File Size** | — |\n"
                        "| **Format** | — |\n"
                        "| **Audio Quality** | — |\n\n"
                        "*Generate an audiobook to see export statistics.*"
                    )

            # ================================================================
            # TAB 5 — 📊 STATISTICS
            # ================================================================
            with gr.TabItem("📊 Statistics"):
                gr.Markdown(
                    "### Usage Statistics\n"
                    "Track your audiobook creation history, cache performance, "
                    "and total output metrics across all sessions."
                )

                # ── Summary cards ─────────────────────────────────────────────
                with gr.Row():
                    with gr.Column(elem_classes="stat-card"):
                        gr.Markdown("#### 🎧 Audiobooks Created")
                        total_books_md = gr.Markdown("**0**")

                    with gr.Column(elem_classes="stat-card"):
                        gr.Markdown("#### ⏱️ Total Hours Generated")
                        total_hours_md = gr.Markdown("**0 h 0 m**")

                    with gr.Column(elem_classes="stat-card"):
                        gr.Markdown("#### 💾 TTS Cache Size")
                        cache_size_md = gr.Markdown("**0 MB**")

                    with gr.Column(elem_classes="stat-card"):
                        gr.Markdown("#### 🔄 Cache Hits")
                        cache_hits_md = gr.Markdown("**0**")

                refresh_stats_btn = gr.Button("🔄  Refresh Statistics", size="sm")

                # ── Job history ───────────────────────────────────────────────
                gr.Markdown("#### 📜 Job History")
                job_history_df = gr.Dataframe(
                    headers=["Job ID", "Title", "Engine", "Duration", "Status", "Created At"],
                    datatype=["str", "str", "str", "str", "str", "str"],
                    interactive=False,
                    wrap=True,
                    label="Historical Jobs",
                )

                # ── Cache management ──────────────────────────────────────────
                with gr.Accordion("🗑️  Cache Management", open=False):
                    gr.Markdown(
                        "The TTS segment cache stores generated audio clips so that "
                        "unchanged segments are never re-synthesised.  Clear only if "
                        "you want to force a full regeneration or reclaim disk space."
                    )
                    with gr.Row():
                        clear_cache_btn = gr.Button(
                            "🗑️  Clear Cache", variant="stop", size="sm"
                        )
                        cache_action_md = gr.Markdown("")

        # ====================================================================
        # EVENT WIRING
        # ====================================================================

        # ── Parse ────────────────────────────────────────────────────────────

        def _parse_and_open(
            file_obj: Any,
            url: str,
            text: str,
            engine: str,
        ) -> Tuple:
            chapters, analysis, time_est, _log = parse_book_handler(
                file_obj, url, text, engine
            )
            return (
                chapters,
                analysis,
                time_est,
                time_est,
                gr.update(open=True),
                chapters,
            )

        parse_btn.click(
            fn=_parse_and_open,
            inputs=[input_file, input_url, input_text, engine_radio],
            outputs=[
                chapter_list_df,
                analysis_stats_md,
                time_estimate_md,
                time_estimate_gen_md,
                analysis_accordion,
                parsed_chapters,
            ],
        )

        # ── Engine change → repopulate voice dropdowns ───────────────────────

        def _update_voices(engine: str) -> Tuple[Any, Any]:
            voices = get_voices_for_engine(engine)
            narrator_val = voices[0]
            dialogue_val = voices[1] if len(voices) > 1 else voices[0]
            s = load_settings()
            s["engine"] = engine
            save_settings(s)
            return (
                gr.update(choices=voices, value=narrator_val),
                gr.update(choices=voices, value=dialogue_val),
            )

        engine_radio.change(
            fn=_update_voices,
            inputs=[engine_radio],
            outputs=[narrator_voice_dd, dialogue_voice_dd],
        )

        # ── Voice preview ────────────────────────────────────────────────────

        narrator_preview_btn.click(
            fn=preview_voice_handler,
            inputs=[narrator_voice_dd, engine_radio],
            outputs=[narrator_preview_audio],
        )
        dialogue_preview_btn.click(
            fn=preview_voice_handler,
            inputs=[dialogue_voice_dd, engine_radio],
            outputs=[dialogue_preview_audio],
        )

        # ── Pronunciation preset ──────────────────────────────────────────────

        load_preset_btn.click(
            fn=load_pronunciation_preset,
            inputs=[preset_dd],
            outputs=[pronunciation_df],
        )

        # ── Generate ─────────────────────────────────────────────────────────

        def _generate(
            chapters: List[List[Any]],
            engine: str,
            narrator_voice: str,
            dialogue_voice: str,
            char_voices: List[List[Any]],
            pron_overrides: List[List[str]],
            speed: float,
            output_format: str,
            normalize: bool,
            export_preset: str,
            bg_music: Optional[Any],
            bg_vol: float,
            cancel: bool,
            progress: gr.Progress = gr.Progress(),
        ) -> Tuple:
            # Persist latest settings before starting
            s = load_settings()
            s.update(
                {
                    "engine": engine,
                    "narrator_voice": narrator_voice,
                    "dialogue_voice": dialogue_voice,
                    "speed": speed,
                    "output_format": output_format,
                    "normalize": normalize,
                    "export_preset": export_preset,
                    "bg_music_volume": bg_vol,
                }
            )
            save_settings(s)

            # Reset cancel flag at start of new run
            log_text, status, ch_rows, out_path = generate_handler(
                chapters,
                engine,
                narrator_voice,
                dialogue_voice,
                char_voices,
                pron_overrides,
                speed,
                output_format,
                normalize,
                export_preset,
                getattr(bg_music, "name", None) if bg_music else None,
                bg_vol,
                cancel,
                progress,
            )
            return log_text, status, ch_rows, out_path, out_path

        generate_btn.click(
            fn=_generate,
            inputs=[
                parsed_chapters,
                engine_radio,
                narrator_voice_dd,
                dialogue_voice_dd,
                character_voices_df,
                pronunciation_df,
                speed_slider,
                output_format_radio,
                normalize_chk,
                export_preset_radio,
                bg_music_file,
                bg_volume_slider,
                cancel_state,
            ],
            outputs=[
                gen_log_tb,
                status_md,
                chapter_progress_df,
                output_audio_player,
                download_file,
            ],
        )

        # ── Stop ─────────────────────────────────────────────────────────────

        stop_btn.click(
            fn=lambda: (True, "⛔  **Generation stopped by user.**"),
            inputs=[],
            outputs=[cancel_state, status_md],
        )

        # ── Resume ───────────────────────────────────────────────────────────

        def _resume() -> Tuple[bool, str]:
            """Attempt to resume from the most recent generation manifest."""
            print("[resume_handler] Resuming from manifest — stub")
            # Wire up: ManifestManager.load_latest() and re-enter generate pipeline
            return False, "↩️  **Resuming from last checkpoint…** *(stub — wire ManifestManager)*"

        resume_btn.click(
            fn=_resume,
            inputs=[],
            outputs=[cancel_state, status_md],
        )

        # ── Bookmarks ────────────────────────────────────────────────────────

        add_bookmark_btn.click(
            fn=add_bookmark_handler,
            inputs=[current_position_state, bookmarks_df],
            outputs=[bookmarks_df],
        )

        # ── Theme toggle (label only — full CSS swap requires JS injection) ──

        def _toggle_theme_label(current_label: str) -> Tuple[Any, Dict[str, Any]]:
            if "Light" in current_label:
                new_label = "🌙  Dark Mode"
            else:
                new_label = "☀️  Light Mode"
            s = load_settings()
            s["theme_label"] = new_label
            save_settings(s)
            return gr.update(value=new_label)

        theme_toggle_btn.click(
            fn=_toggle_theme_label,
            inputs=[theme_toggle_btn],
            outputs=[theme_toggle_btn],
        )

        # ── Statistics refresh ────────────────────────────────────────────────

        def _refresh_stats() -> Tuple:
            cache = get_cache_stats()
            total_secs = _stats["total_seconds"]
            hours = total_secs // 3600
            minutes = (total_secs % 3600) // 60

            history_rows = [
                [
                    j["job_id"][:8] + "…",
                    j.get("title", "Unknown"),
                    j.get("engine", "—"),
                    "—",
                    j.get("status", "—").capitalize(),
                    j.get("created_at", "—"),
                ]
                for j in _jobs.values()
            ]

            return (
                f"**{_stats['total_books']}**",
                f"**{hours} h {minutes} m**",
                f"**{cache['size_mb']} MB**",
                f"**{cache['hits']}**",
                history_rows,
            )

        refresh_stats_btn.click(
            fn=_refresh_stats,
            inputs=[],
            outputs=[
                total_books_md,
                total_hours_md,
                cache_size_md,
                cache_hits_md,
                job_history_df,
            ],
        )

        # ── Clear cache ───────────────────────────────────────────────────────

        def _clear_cache() -> str:
            cache_dir = Path("tts_cache")
            cleared = 0
            if cache_dir.exists():
                for f in cache_dir.rglob("*"):
                    if f.is_file():
                        try:
                            f.unlink()
                            cleared += 1
                        except Exception:
                            pass
            print(f"[clear_cache] Removed {cleared} cached segments.")
            return f"✅  Cache cleared — {cleared} segment files removed."

        clear_cache_btn.click(
            fn=_clear_cache,
            inputs=[],
            outputs=[cache_action_md],
        )

    return app


# ---------------------------------------------------------------------------
# FastAPI REST API
# ---------------------------------------------------------------------------

api = FastAPI(
    title="Audiobook Creator V7 API",
    version="7.0.0",
    description=(
        "REST interface for the Audiobook Creator V7 pipeline. "
        "Supports starting generation jobs, polling status, cancellation, "
        "and voice discovery."
    ),
)


class GenerationRequest(BaseModel):
    """Payload for starting a new audiobook generation job."""

    source_type: str  # "file_path" | "url" | "text"
    source: str       # filesystem path, public URL, or raw text content
    title: str
    author: str = ""
    engine: str = "edge-tts"
    narrator_voice: str = "en-US-GuyNeural"
    output_format: str = "m4b"


class GenerationStatus(BaseModel):
    """Current status snapshot for a generation job."""

    job_id: str
    status: str          # "parsing" | "generating" | "assembling" | "complete" | "error"
    progress_percent: float
    segments_done: int
    segments_total: int
    output_path: Optional[str] = None
    error_message: Optional[str] = None


def _run_generation_job(job_id: str, request: GenerationRequest) -> None:
    """
    Background task: simulate (or execute) the full generation pipeline.

    In production, replace the stub loop with:
        ManifestManager → parse → per-segment TTS → assemble → encode_to_m4b
    """
    try:
        _jobs[job_id]["status"] = "parsing"
        time.sleep(1)  # stub: parsing phase

        _jobs[job_id].update({"status": "generating", "segments_total": 100})
        for i in range(1, 101):
            if _jobs[job_id].get("cancelled"):
                _jobs[job_id].update(
                    {"status": "error", "error_message": "Cancelled by user."}
                )
                return
            _jobs[job_id]["segments_done"] = i
            _jobs[job_id]["progress_percent"] = float(i)
            time.sleep(0.05)  # stub: per-segment work

        _jobs[job_id]["status"] = "assembling"
        time.sleep(1)  # stub: assembly

        output_path = f"/tmp/{job_id}.{request.output_format}"
        _jobs[job_id].update(
            {"status": "complete", "output_path": output_path}
        )
        _stats["total_books"] += 1

    except Exception as exc:
        _jobs[job_id].update(
            {"status": "error", "error_message": str(exc)}
        )


def _job_to_status(job: Dict[str, Any]) -> GenerationStatus:
    """Extract only the GenerationStatus fields from a raw job dict."""
    return GenerationStatus(
        job_id=job["job_id"],
        status=job["status"],
        progress_percent=job["progress_percent"],
        segments_done=job["segments_done"],
        segments_total=job["segments_total"],
        output_path=job.get("output_path"),
        error_message=job.get("error_message"),
    )


@api.post("/generate", response_model=GenerationStatus, status_code=202)
async def start_generation(
    request: GenerationRequest,
    background_tasks: BackgroundTasks,
) -> GenerationStatus:
    """
    Start a new audiobook generation job.

    Returns a **202 Accepted** response with the initial job status.
    Poll `/status/{job_id}` to track progress.
    """
    job_id = str(uuid.uuid4())
    _jobs[job_id] = {
        "job_id": job_id,
        "status": "parsing",
        "progress_percent": 0.0,
        "segments_done": 0,
        "segments_total": 0,
        "output_path": None,
        "error_message": None,
        "title": request.title,
        "engine": request.engine,
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "cancelled": False,
    }
    background_tasks.add_task(_run_generation_job, job_id, request)
    return _job_to_status(_jobs[job_id])


@api.get("/status/{job_id}", response_model=GenerationStatus)
async def get_status(job_id: str) -> GenerationStatus:
    """Retrieve the current status and progress of a generation job."""
    if job_id not in _jobs:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")
    return _job_to_status(_jobs[job_id])


@api.post("/cancel/{job_id}")
async def cancel_job(job_id: str) -> Dict[str, str]:
    """Request cancellation of a running generation job."""
    if job_id not in _jobs:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")
    if _jobs[job_id]["status"] in ("complete", "error"):
        raise HTTPException(
            status_code=409,
            detail=f"Job '{job_id}' is already {_jobs[job_id]['status']}.",
        )
    _jobs[job_id]["cancelled"] = True
    return {"message": f"Cancellation requested for job '{job_id}'."}


@api.get("/voices/{engine}")
async def list_voices(engine: str) -> Dict[str, Any]:
    """
    List available voices for the specified TTS engine.

    *engine* should be one of: ``edge-tts``, ``kokoro``.
    """
    normalised = engine.lower().replace("-", "").replace("_", "")
    if "kokoro" in normalised:
        voices = KOKORO_VOICES
        engine_label = "Kokoro (Offline, CPU)"
    else:
        voices = EDGE_TTS_VOICES
        engine_label = "edge-tts (Cloud, Free)"
    return {"engine": engine_label, "voice_count": len(voices), "voices": voices}


@api.get("/health")
async def health_check() -> Dict[str, str]:
    """Return API health status and version information."""
    return {
        "status": "healthy",
        "version": "7.0.0",
        "active_jobs": str(
            sum(1 for j in _jobs.values() if j["status"] in ("parsing", "generating", "assembling"))
        ),
    }


# ---------------------------------------------------------------------------
# App Entry Point
# ---------------------------------------------------------------------------


def launch_app(
    share: bool = False,
    port: int = 7860,
    api_port: int = 7861,
) -> None:
    """
    Launch both the Gradio UI and the FastAPI REST API.

    The FastAPI server starts in a background daemon thread so it does not
    block the Gradio event loop.  Both services bind to ``0.0.0.0`` to allow
    access from the host machine when running inside a container or VM.

    Args:
        share:    If True, create a public Gradio tunnel link via the
                  Gradio share infrastructure.
        port:     TCP port for the Gradio web UI.
        api_port: TCP port for the FastAPI REST API.
    """
    def _run_api() -> None:
        uvicorn.run(api, host="0.0.0.0", port=api_port, log_level="warning")

    api_thread = threading.Thread(
        target=_run_api, daemon=True, name="fastapi-server"
    )
    api_thread.start()

    print(f"[Audiobook Creator V7] REST API  →  http://localhost:{api_port}")
    print(f"[Audiobook Creator V7] API docs  →  http://localhost:{api_port}/docs")
    print(f"[Audiobook Creator V7] UI        →  http://localhost:{port}")

    ui = build_ui()
    ui.launch(
        server_name="0.0.0.0",
        server_port=port,
        share=share,
        show_error=True,
        favicon_path=None,
        quiet=False,
        theme=_build_theme(),
        css=_CUSTOM_CSS,
    )


# ---------------------------------------------------------------------------

if __name__ == "__main__":
    launch_app()
