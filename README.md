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
- Works as a PWA (installable, offline-friendly shell).

### API routes

| Route | Method | Purpose |
|-------|--------|---------|
| `GET /api/voices` | | List curated neural voices (`{ voices, default }`). |
| `POST /api/tts` | | Synthesize one chunk. Body: `{ text, voice, rate, pitch, volume, format }`. Returns `audio/mpeg`. |
| `GET /api/health` | | Service health check. |
| `GET /api/launch` | | Launcher metadata & instructions. |

Example:

```bash
curl -X POST https://your-deployment.vercel.app/api/tts \
  -H "Content-Type": "application/json" \
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

Open http://localhost:8002 (or the port shown).

## Optional Premium Voices (ElevenLabs)

The web maker (`web/index.html`) now includes a **"Premium voices (optional)"** section for dramatically more emotional and natural narration:

- Toggle "Use premium for this generation".
- Enter your ElevenLabs API key (never sent to our servers — stored only in your browser's `localStorage` and used for direct `https://api.elevenlabs.io` calls from the client).
- Choose model (Turbo v2.5 recommended for books; Multilingual v2 for max quality).
- Pick from popular stock voices or load your own cloned voices via the "Load my voices" button.
- Existing `style` (dramatic/gentle/etc) + `expressiveness` sliders are automatically mapped to ElevenLabs `voice_settings` (`stability`, `style`, `similarity_boost`).
- **Improved mapping**: High expressiveness (common with "Auto-detect" style + emotional text) now drives lower stability + higher style exaggeration for more dynamic, performed delivery on high-express samples.

**Free path stays the default** (Microsoft Edge neural + rich SSML). Premium is 100% opt-in and easy to switch off.

### Optional secure server-side proxy (advanced / self-hosted)

For deployments where you want to offer premium ElevenLabs **without any API key ever entering the user's browser or localStorage**:

- Create a new small route at `api/elevenlabs.js` (registered automatically in dev server + vercel.json).
- Set the `ELEVENLABS_API_KEY` environment variable on your hosting platform (Vercel, etc.).
- In the UI, check the small **"Use secure server proxy"** checkbox (off by default, clearly labeled).
- The client then POSTs the exact same payload shape (text + voice_id + model_id + computed voice_settings) to `/api/elevenlabs`.
- The server proxies to ElevenLabs using only the env var key and streams audio back.
- If the env var is missing, the endpoint returns a clear 503 with instructions to fall back to the (excellent) client-side direct path.
- Voices list also works via the proxy when enabled (`?voices=1`).

This is **completely optional**, zero-config for the vast majority of users, and documented as an advanced/self-hosted feature. The primary recommended path remains the direct client integration.

### Getting an ElevenLabs key
1. Sign up at [elevenlabs.io](https://elevenlabs.io).
2. Go to [API Keys](https://elevenlabs.io/app/settings/api-keys).
3. Create a key (start with free tier for testing).

### Cost notes
- ElevenLabs charges per-character.
- Rough estimate (Turbo): a 100,000 character book is typically well under $1 on paid plans. Free tier includes monthly character quota.
- Always monitor usage at elevenlabs.io. If you hit quota/limits you will see an error — simply uncheck the premium toggle to instantly fall back to the free Edge path.
- OpenAI TTS (`/v1/audio/speech`) is a straightforward alternative client-side path if preferred (similar key-in-localStorage pattern).

The implementation keeps the exact same multi-chunk + parallel orchestration for both paths. No backend changes were required for the default experience.

## License

MIT

## Voice Quality & Emotion (Major 2026 Update)
The free Edge neural voices are now dramatically more natural and emotional thanks to a full rich SSML engine (auto emotion detection, dialogue-aware prosody, strategic pauses, emphasis, and mstts:express-as styles).

**In the web app:**
- Set **Narration Style** to "Auto (detect...)" for best results — it scans your text for emotional cues and applies the right delivery.
- Crank **Expressiveness** (70-90% recommended for fiction).
- Styles like Dramatic, Intense, Sarcastic, Whispering now produce audible warmth, lifts on questions/dialogue, and real feeling instead of robotic flatness.

Example emotional paragraph now gets proper breaks, emphasis on "Suddenly", question pitch shifts, and style wrapping.

Desktop Gradio app now has full parity (Narration Style + Expressiveness controls + rich emotional SSML on Edge engine).

**Powerful new tuning tool**: `tests/voice-emotion-samples/` contains a research-derived emotional corpus (13 paragraphs covering dialogue, questions, exclamations, em-dashes, mixed tones: sad, angry, ecstatic, sarcastic, whispering, dramatic) + runnable generators (`generate.js --write` and the lightweight `generate-ab.js`). After any change to the SSML builder or Python port, run it to instantly see layered rich SSML output with autoDetect triggers, roles, breaks, emphasis, etc. The `outputs/` folder has ready artifacts for A/B testing with the web "Debug SSML" viewer or direct synthesis. This is the fastest way to keep making voices more human.

Test with the One-Click Demo — it now defaults to Auto + high emotion.

This was the #1 user request and is the current top priority. More premium options (ElevenLabs-style) coming.