# Audiobook Maker V7

Manifest-based audiobook generator with a Gradio UI and a 3-stage pipeline:

1. **Parse** (book text -> manifest)
2. **Generate** (manifest -> cached TTS segment audio)
3. **Assemble** (segments -> final MP3/M4B audiobook)

Main entrypoint: `audiobook_creator_v7.py`

## Quick Start

```bash
pip install -r requirements.txt
python3 audiobook_creator_v7.py
```

Then open: `http://localhost:7860`

## What is implemented

- Single-file V7 app (`audiobook_creator_v7.py`)
- Manifest save/load and resume-friendly checkpointing
- TTS engine abstraction (`edge-tts`, `kokoro`)
- Segment audio cache with LRU eviction
- Pronunciation override support
- FFmpeg-based assembly, optional loudness normalization, M4B chapter metadata
- Gradio tabs: Input, Voices, Generate, Player

## Reliability Improvements Included

- Atomic JSON writes for manifest/cache index updates
- Automatic manifest backup recovery from `*.bak`
- Cache validation (duration/checksum/size) with stale entry cleanup
- Bounded-queue generation workers for low-memory machines
- Assembly checkpoints for safer resume after interruptions
- FFmpeg timeout/retry wrapper for more robust long runs
- Explicit run-state tracking (`idle`, `generating`, `assembling`, `cancelled`, `failed`, `completed`)
- System preflight diagnostics tab in UI
- Runtime output folders auto-created
- Optional dependency fallbacks (graceful degradation)
- Basic cancel handling during generation
- `.gitignore` added for generated runtime artifacts

## Free Cloud Memory (optional)

The app now supports **free anonymous cloud manifest memory** using JSONBlob:

- In the UI, enable **"Enable free cloud memory backup (JSONBlob)"**
- Use the **System** tab to:
  - Backup current manifest to cloud
  - Restore a manifest from a cloud URL

This stores JSON manifest state remotely, so you can resume from another machine without paid infrastructure.

> Note: this is for manifest/progress memory, not audio-file hosting.

## Vercel Website Launcher

This repo includes a lightweight Vercel launcher website so visitors can discover how to run the local Gradio app.

### Launcher files

- `vercel.json` - routes `/` to the launcher page and exposes `/api/launch`
- `website/index.html` - static launcher UI with quick-start commands
- `api/launch.js` - JSON instructions endpoint

### Deploy to Vercel

1. Push repository to GitHub
2. Import it in Vercel as a new project
3. Deploy with default settings

After deployment:

- `/` shows the launcher page
- `/api/launch` returns machine-readable launch instructions
