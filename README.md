# Audiobook Creator v7

Convert any book (EPUB, PDF, TXT, or URL) into a finished audiobook MP3 or M4B file using AI voice synthesis.

## Features
- Multi-voice dialogue detection (narrator vs. characters get different voices)
- Offline TTS support -- no API key required for basic use
- Smart caching -- interrupted jobs resume instantly
- Mobile-first Gradio UI with live progress updates
- M4B chapter markers with accurate timestamps
- Pronunciation dictionary support

## Quick Start (Local)
```bash
pip install -r requirements.txt
python audiobook_creator_v7.py
```
Open http://localhost:7860 in your browser.
Login: admin / audiobook2024

## Deploy to Hugging Face Spaces
1. Create a new Space at huggingface.co (select Gradio)
2. Connect your GitHub repo cajub311/audiobook-maker-
3. Set Space hardware to CPU Basic (free)
4. Your app will be live at https://cajub311-audiobook-maker.hf.space

## Deploy Frontend to Vercel
1. Import cajub311/audiobook-maker- at vercel.com/new
2. Add environment variable: GRADIO_SERVER_URL = your HF Space URL
3. Deploy -- no build settings needed

## Auth
Default credentials: admin / audiobook2024
Change in audiobook_creator_v7.py at the demo.launch() call.

## License
MIT
