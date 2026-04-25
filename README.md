# Audiobook Maker

Turn any text into a real MP3 audiobook — in your browser, free, with no sign-up and no API key.

This repo ships **two** ways to use it:

1. **Web audiobook maker** (`/web/index.html`) — a serverless app that runs on Vercel. It calls Microsoft Edge's neural Read Aloud API via a small Node backend and streams real MP3 audio back to the browser. Perfect for quick audiobook generation on a phone or laptop.
2. **Desktop Python app** (`audiobook_creator_v7.py`) — a fuller Gradio UI for advanced users who want multi-voice dialogue, chapter markers, resume support, and offline generation via Kokoro.

## Web audiobook maker (default)

Open `/web/index.html` after deploying, paste text, pick a voice, press **Create audiobook**, and download the MP3.

- 30+ hand-picked Microsoft neural voices across 10+ languages.
- Long inputs are auto-split on paragraph/sentence boundaries.
- Chunks render **in parallel** (configurable, default 4) for fast generation.
- Voice preview, reading speed, pitch control.
- Saves your draft locally and restores it on reload.
- **Multi-voice**: builds a **cast list** from the whole book (speech tags, `*Name*`, `First Last` + narration verbs, `Name walked` / `Sarah frowned`, etc.), resolves **`she` / `he` / `they` + said** before and after quotes, chains **`"…" she said. "More"`** to the same speaker, treats **`"Mark?"`** as the other character when the cast is known, and uses **Speaker A / B** only when still unknown. Fixes a bug where case-insensitive regex stripped **`she said`** as if it were a capitalized name.
- Works as a PWA (installable, offline-friendly shell).

### API routes

| Route | Method | Purpose |
|-------|--------|---------|
| `GET /api/voices` | | List curated neural voices (`{ voices, default }`). |
| `POST /api/tts` | | Synthesize one chunk. Body: `{ text, voice, rate, pitch, volume, format }`. Returns `audio/mpeg`. |
| `POST /api/process` | | Demo async job (returns `job_id` + `poll_url`; text length capped). |
| `GET /api/health` | | Service health check. |
| `GET /api/launch` | | Launcher metadata & instructions. |

Example:

```bash
curl -X POST https://your-deployment.vercel.app/api/tts \
  -H "Content-Type: application/json" \
  -d '{"text":"Hello, this is an audiobook.","voice":"en-US-AvaMultilingualNeural"}' \
  --output sample.mp3
```

### Deploy to Vercel

1. Import this repo at [vercel.com/new](https://vercel.com/new).
2. Node 18+ is required. No environment variables needed.
3. Click Deploy. `npm install` automatically brings in `msedge-tts`.

### Run locally

```bash
npm install
npx vercel dev      # or: npm run test
```

The included tests exercise the TTS handler's validation and run against `/api/tts`, `/api/voices`, and the text chunker.

## Desktop Python app (advanced)

```bash
pip install -r requirements.txt
# optional: ./setup.sh   # same deps + checks FFmpeg and TTS engines
python audiobook_creator_v7.py
```

Open http://localhost:7860. The Gradio UI is password-protected by default. Set **`GRADIO_AUTH_USER`** and **`GRADIO_AUTH_PASSWORD`** before launch to pick your own credentials (defaults remain `admin` / `audiobook2024`). For **local development only**, you can disable login with **`ABM_GRADIO_NO_AUTH=1`** — do not expose that mode to the public internet.

Public link sharing still uses **`GRADIO_SHARE=1`** (unchanged).

Features: multi-voice dialogue, M4B with chapter markers, pronunciation dictionary, PDF/EPUB/URL ingest, resume-safe caching.

## License

MIT
