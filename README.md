# Audiobook Maker V7

Manifest-based audiobook generator with a Gradio UI and a 3-stage pipeline:

1. **Parse** (book text -> manifest)
2. **Generate** (manifest -> cached TTS segment audio)
3. **Assemble** (segments -> final MP3/M4B audiobook)

Main entrypoint: `audiobook_creator_v7.py`

Repository display name (recommended): **`audiobook-maker`** (without trailing dash).

## Quick Start

```bash
pip install -r requirements.txt
python3 audiobook_creator_v7.py
```

Then open: `http://localhost:7860`

## Screenshots

### Gradio UI Preview

![Audiobook Maker V7 UI](assets/gradio-ui-preview.svg)

### Launcher Preview

- Root launcher: `/`
- Secondary launcher page: `/website/index.html`

### Phone / Mobile Quick Start

- Open the app and use **Easy Mobile Mode** tab.
- Choose `Paste Text`, `URL`, or `File`.
- Tap **Generate Audiobook Now** (one-button flow).
- Play and download from the same screen.
- Optional: enable free cloud memory backup to continue later on another device.
- Your input draft and selected source are auto-remembered for next launch.
- Use **Resume Last Project** in the sidebar to continue quickly.

If you want a temporary public link for your phone, run:

```bash
GRADIO_SHARE=1 python3 audiobook_creator_v7.py
```

## What is implemented

- Single-file V7 app (`audiobook_creator_v7.py`)
- Manifest save/load and resume-friendly checkpointing
- TTS engine abstraction (`edge-tts`, `kokoro`)
- Segment audio cache with LRU eviction
- Pronunciation override support
- FFmpeg-based assembly, optional loudness normalization, M4B chapter metadata
- Gradio tabs: Input, Voices, Generate, Player
- Mobile-friendly Easy Mode with simplified one-tap generation path

## Reliability Improvements Included

- Atomic JSON writes for manifest/cache index updates
- Automatic manifest backup recovery from `*.bak`
- Cache validation (duration/checksum/size) with stale entry cleanup
- Bounded-queue generation workers for low-memory machines
- Assembly checkpoints for safer resume after interruptions
- FFmpeg timeout/retry wrapper for more robust long runs
- Explicit run-state tracking (`idle`, `parsed`, `generated`, `assembling`, `cancelled`, `failed`, `completed`)
- System preflight diagnostics tab in UI
- URL safety guard for remote fetches (blocks private-network targets)
- Unique temp generation filenames to avoid parallel write collisions
- Quick mode auto-fallback from edge-tts to offline Kokoro when needed
- Draft persistence (`ui_draft.json`) for phone text/url/file workflows
- Last-project resume memory (`app_state.json`) and one-tap resume button
- Per-book memory for character voices + pronunciation overrides (`pronunciations/book_profiles`)
- Sidebar scans manifest + cloud + output files, with one-tap **Open Output** playback
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

This repo includes a modern Tailwind-powered Vercel launcher website so mobile users can quickly start the Gradio app and follow guided steps.

### Launcher files

- `index.html` - root launcher page (primary Vercel entrypoint)
- `website/index.html` - alternate launcher page with same modern layout
- `vercel.json` - minimal Vercel settings (`cleanUrls`, no trailing slash)
- `.vercelignore` - excludes local runtime data from deployment payload
- `manifest.webmanifest`, `service-worker.js`, `icon.svg` - mobile PWA-style launcher support
- `assets/gradio-ui-preview.svg` - hero/screenshot artwork used by launcher pages
- `api/launch.js`, `api/health.js` - JSON instruction + health endpoints

### Launcher highlights

- Tailwind CDN responsive redesign (mobile-first)
- Dark mode toggle matching app vibe
- Hero + screenshot + feature cards
- Command cards with copy-to-clipboard buttons
- Phone workflow visual
- PWA install prompt banner
- GitHub star + version badge + Hugging Face teaser

### CI checks

GitHub Actions workflow at `.github/workflows/ci.yml` runs:
- Python syntax compile check
- Reliability unit tests
- Node smoke test for `/api/launch` handler

### Deploy to Vercel

1. Push repository to GitHub
2. Import it in Vercel as a new project
3. Deploy with default settings

After deployment:

- `/` shows the launcher page
- `/api/launch` returns machine-readable launch instructions

### If Vercel shows 404 NOT_FOUND

1. In Vercel Project Settings, set **Root Directory** to repository root (`.`)
2. Use framework preset **Other**
3. Redeploy latest commit from `main`
