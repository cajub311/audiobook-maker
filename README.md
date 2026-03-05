# Audiobook Creator V7

Turn any book (EPUB, PDF, TXT) into a professional audiobook with neural TTS, character voices, and smart chapter detection.

## Features

- **Multi-format input:** EPUB, PDF, TXT, URL, or pasted text
- **Neural TTS:** Edge-TTS (cloud, free) or Kokoro (offline, CPU)
- **Character voices:** Auto-detect dialogue, assign voices per character
- **Chapter detection:** From TOC, headings, or font size
- **Resume & cache:** Manifest-based pipeline, stop and resume anytime
- **Low-spec friendly:** Runs on 2 cores, 3.4GB RAM

## Quick Start

```bash
pip install -r requirements.txt
python app.py   # or audiobook_creator_v7.py when single-file build is ready
```

Opens Gradio UI at `http://localhost:7860`.

## Project Structure

```
├── src/                    # Modular implementation (chunks)
├── tests/
├── web/                    # Vercel landing page (Next.js)
├── audiobook_v7_handoff.md  # Full architecture & implementation spec
├── IMPLEMENTATION_PLAN.md   # Multi-agent chunk strategy & deployment
└── requirements.txt
```

## Multi-Agent Implementation

See **[IMPLEMENTATION_PLAN.md](./IMPLEMENTATION_PLAN.md)** for:

- 11 implementation chunks (parallelizable)
- Agent launch order and dependencies
- GitHub branch/PR workflow
- Improvements to the handoff
- Vercel website deployment

## Deployment

### Gradio App

- **Local:** `python app.py`
- **Hugging Face Spaces:** Push to a Space with Gradio SDK
- **Docker:** (Dockerfile coming in Chunk 11)

### Landing Page (Vercel)

1. Connect this repo to [Vercel](https://vercel.com)
2. Set **Root Directory** to `web`
3. Deploy — Next.js is auto-detected

Or from CLI:

```bash
cd web && vercel
```

## Requirements

- Python 3.11+
- FFmpeg on PATH
- 3.4GB+ RAM (for long books)

## License

Open source. See repo for details.
