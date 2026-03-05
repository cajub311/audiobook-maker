# Audiobook Creator V7

Convert EPUB, PDF, TXT books or web pages into fully-chaptered **M4B / MP3 audiobooks** with per-character voices, pronunciation overrides, and professional loudness normalization — all from a clean browser UI.

---

## Features

| Feature | Detail |
|---------|--------|
| **Input formats** | EPUB, PDF, TXT, URL (web article) |
| **TTS engines** | Edge-TTS (cloud, free, 12× parallel) · Kokoro ONNX (offline, CPU) |
| **Output formats** | M4B with chapter markers · MP3 |
| **Character voices** | Auto-detects dialogue speakers; assigns unique voices per character |
| **Pronunciations** | Per-book word → phonetic replacement (fantasy name support built-in) |
| **Loudness** | Two-pass EBU R128 normalization, −19 LUFS (audiobook standard) |
| **Resume** | Manifest-based pipeline — stop and resume at any segment |
| **REST API** | FastAPI endpoint for programmatic integration |
| **Cache** | LRU disk cache with configurable size limit |
| **SSML / Emotion** | Detects exclamations/questions and applies prosody hints |

---

## Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt
python -m spacy download en_core_web_sm

# 2. Ensure FFmpeg is on your PATH
# Windows: choco install ffmpeg  OR  https://ffmpeg.org/download.html
# Linux:   sudo apt install ffmpeg

# 3. Run
python audiobook_creator_v7.py
# → opens at http://localhost:7860
```

Optional flags:
```bash
python audiobook_creator_v7.py --share        # Public Gradio share link
python audiobook_creator_v7.py --port 8080    # Custom Gradio port
python audiobook_creator_v7.py --no-api       # Disable REST API (port 7861)
```

---

## Offline TTS (Kokoro)

```bash
pip install kokoro-onnx soundfile

# Download model files (~80 MB, one-time):
# Place these files in any of: ~/.cache/kokoro  ~/kokoro  /opt/kokoro  ./
#   kokoro-v1.0.onnx   (full precision) OR  kokoro-v1.0-q8.onnx  (faster)
#   voices-v1.0.bin
```

Model files: [huggingface.co/hexgrad/Kokoro-82M](https://huggingface.co/hexgrad/Kokoro-82M)

---

## Architecture

```
audiobook_creator_v7.py     ← Entry point; wires pipeline into UI
src_manifest.py             ← ManifestManager, AudioCache (LRU), pipeline stages
src_tts_audio.py            ← TTS engines (EdgeTTS, Kokoro), FFmpeg wrappers
src_text_processor.py       ← Book parsers, chapter detection, character NLP
src_ui.py                   ← 5-tab Gradio UI + FastAPI REST API
```

### 3-Stage Pipeline

```
Stage 1 — Parse      Book file/URL → manifest.json
                     (chapters, segments, speakers, cache keys)

Stage 2 — Generate   manifest → per-segment MP3 files
                     (TTS synthesis, parallel async, LRU cache)

Stage 3 — Assemble   cache files → final .m4b / .mp3
                     (FFmpeg concat → optional music → loudnorm → M4B)
```

---

## REST API

The REST API starts automatically on `http://localhost:7861`:

```bash
# Generate an audiobook
curl -X POST http://localhost:7861/generate \
  -H "Content-Type: application/json" \
  -d '{"source_type":"file_path","source":"/path/to/book.epub","title":"My Book","engine":"edge-tts"}'

# Check status
curl http://localhost:7861/status/{job_id}

# List available voices
curl http://localhost:7861/voices/edge-tts

# Health check
curl http://localhost:7861/health
```

Interactive docs at `http://localhost:7861/docs`

---

## Character Detection

The NLP pipeline achieves ~85–90% dialogue attribution accuracy using three layers:

1. **Regex** — 3 patterns × 50 speech verbs → ~70% of dialogue
2. **spaCy NER** — `en_core_web_sm` entity recognition → +15–20%
3. **Alternation Tracker** — A-B-A-B pattern inference → +10%

Unattributed dialogue falls back to the narrator voice.

---

## Pronunciation Overrides

Built-in presets for:
- *Demon Cycle* (Peter V. Brett) — 21 entries
- *Wheel of Time* (Robert Jordan) — 24 entries
- *Dune* (Frank Herbert) — 24 entries

Or add your own in the **Voices** tab → Pronunciation Overrides table.

---

## File Structure

```
audiobook_creator_v7.py     Main entry point
src_manifest.py             Manifest + cache module
src_tts_audio.py            TTS engines + FFmpeg module
src_text_processor.py       Text processing module
src_ui.py                   UI + API module
requirements.txt
website/                    Next.js Vercel landing page

tts_cache/                  LRU audio segment cache (auto-created)
manifests/                  Per-book manifest files (auto-created)
output/                     Final audiobooks (auto-created)
temp/                       FFmpeg working files (auto-created)
pronunciations/             Per-book pronunciation JSON files
```

---

## System Requirements

| Requirement | Minimum | Recommended |
|-------------|---------|-------------|
| CPU | 2 cores | 4+ cores |
| RAM | 3.4 GB | 8 GB |
| Disk | 2 GB (cache) | 10 GB |
| FFmpeg | Required | Latest |
| Python | 3.10+ | 3.11+ |
| Internet | For Edge-TTS | — |

---

## Website / Landing Page

The `website/` directory contains a Next.js landing page deployable to [Vercel](https://vercel.com).

**Deploy to Vercel:**
1. Push this repository to GitHub
2. Import the repo at [vercel.com/new](https://vercel.com/new)
3. Set **Root Directory** to `website`
4. Click **Deploy** — Vercel auto-detects Next.js

Or one-click via Vercel CLI:
```bash
cd website
npm install
npx vercel --prod
```

---

## License

MIT — see [LICENSE](LICENSE)
