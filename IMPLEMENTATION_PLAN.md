# Audiobook Creator V7 — Multi-Agent Implementation Plan

> **Purpose:** Break the handoff into agent-sized chunks, define GitHub workflow, suggest improvements, and add Vercel website deployment.

---

## 1. MULTI-AGENT CHUNK STRATEGY

Split implementation into **independent chunks** that agents can work on in parallel. Each chunk produces testable, mergeable code.

### Chunk 1: Core Manifest & Pipeline Skeleton
**Agent focus:** Foundation only  
**Files:** `manifest.py`, `pipeline.py`, `config.py`  
**Deliverables:**
- Manifest JSON schema (Pydantic/dataclass models)
- `stage_parse()`, `stage_generate()`, `stage_assemble()` stubs with type hints
- Config loading from JSON/env
- Unit tests for manifest validation

**Dependencies:** None  
**Estimated:** 1–2 hours

---

### Chunk 2: TTS Engine Abstraction
**Agent focus:** TTS layer only  
**Files:** `tts/base.py`, `tts/edge_tts.py`, `tts/kokoro.py`  
**Deliverables:**
- `TTSEngine` ABC with `generate()`, `list_voices()`, `preview()`, `max_concurrent`
- `EdgeTTSEngine` full implementation
- `KokoroEngine` full implementation (optional, can stub)
- Integration test: generate 1 segment with edge-tts

**Dependencies:** Chunk 1 (uses manifest types)  
**Estimated:** 2–3 hours

---

### Chunk 3: Text Parsing & Chapter Detection
**Agent focus:** Input → structured text  
**Files:** `parsers/epub.py`, `parsers/pdf.py`, `parsers/txt.py`, `parsers/chapters.py`  
**Deliverables:**
- `yield_chapters_epub()`, `yield_chapters_pdf()`, `yield_chapters_txt()`
- `detect_chapters_epub()`, `detect_chapters_pattern()`, `detect_chapters_pdf_fonts()`
- `detect_scene_breaks()`
- Generator-based streaming (no full-book load)
- Unit tests with sample EPUB/PDF/TXT

**Dependencies:** Chunk 1  
**Estimated:** 2–3 hours

---

### Chunk 4: Character & Dialogue Detection
**Agent focus:** Speaker attribution  
**Files:** `detection/regex_dialogue.py`, `detection/spacy_attributor.py`, `detection/alternation.py`, `detection/pipeline.py`  
**Deliverables:**
- Regex patterns (post/pre/mid dialogue)
- `SpacyAttributor` for unmatched quotes
- `AlternationTracker` for A-B-A-B patterns
- `detect_all_dialogue()` combined pipeline
- Unit tests with sample fiction text

**Dependencies:** Chunk 1  
**Estimated:** 2–3 hours

---

### Chunk 5: Caching & Pronunciation
**Agent focus:** Cache + pronunciation  
**Files:** `cache.py`, `pronunciation.py`  
**Deliverables:**
- `AudioCache` with LRU eviction, `get()`, `put()`, `_enforce_size_limit()`
- `PronunciationDict` with `apply()`, `load()`, `save()`
- Cache key: `MD5(text|voice|engine|speed)`
- Unit tests for cache hit/miss, eviction, pronunciation

**Dependencies:** Chunk 1  
**Estimated:** 1–2 hours

---

### Chunk 6: FFmpeg Assembly
**Agent focus:** Audio assembly only  
**Files:** `ffmpeg_utils.py`, `assembly.py`  
**Deliverables:**
- `get_duration_ffprobe()`
- Silence generation (2s, 1s, 0.5s, 0.3s)
- Concat list builder with gaps
- `normalize_loudness()` two-pass
- `generate_chapter_metadata()` for M4B
- Background music mixing with ducking
- Unit tests (mock FFmpeg, verify command construction)

**Dependencies:** Chunk 1  
**Estimated:** 2–3 hours

---

### Chunk 7: Stage 1 — Parse (Full Integration)
**Agent focus:** Wire Chunks 3, 4, 5 into `stage_parse()`  
**Files:** `stages/parse.py`  
**Deliverables:**
- Full `stage_parse()` implementation
- Chunk text (5500 chars, sentence-aware)
- SFX tag detection `[CRASH]`, `[THUNDER]`
- Cache check for existing segments
- Write `manifest.json`
- Integration test: parse sample EPUB → valid manifest

**Dependencies:** Chunks 1, 3, 4, 5  
**Estimated:** 2 hours

---

### Chunk 8: Stage 2 — Generate (Full Integration)
**Agent focus:** Wire Chunks 2, 5, 6 into `stage_generate()`  
**Files:** `stages/generate.py`  
**Deliverables:**
- Full `stage_generate()` with parallel TTS (12 for edge-tts, 1 for Kokoro)
- Pronunciation override application before TTS
- Manifest update after each segment (resume support)
- `cancel_event` for clean stop
- Progress yielding for UI

**Dependencies:** Chunks 1, 2, 5, 6  
**Estimated:** 2–3 hours

---

### Chunk 9: Stage 3 — Assemble (Full Integration)
**Agent focus:** Wire Chunk 6 into `stage_assemble()`  
**Files:** `stages/assemble.py`  
**Deliverables:**
- Full `stage_assemble()` with concat, loudnorm, M4B metadata
- Cover art embedding
- Return final output path

**Dependencies:** Chunks 1, 6  
**Estimated:** 1–2 hours

---

### Chunk 10: Gradio UI
**Agent focus:** UI only  
**Files:** `ui.py`, `app.py`  
**Deliverables:**
- 4 tabs: Input, Voices, Generate, Player
- Voice dropdowns populated from engine
- Character table, pronunciation table (editable)
- Progress bar, chapter progress, cancel button
- Wire to `stage_parse`, `stage_generate`, `stage_assemble`
- `python app.py` → localhost:7860

**Dependencies:** Chunks 1, 7, 8, 9  
**Estimated:** 3–4 hours

---

### Chunk 11: Single-File Consolidation (Optional)
**Agent focus:** Merge into `audiobook_creator_v7.py`  
**Deliverables:**
- Single-file app per handoff spec
- All imports inlined, no external modules
- Same behavior as modular version

**Dependencies:** All chunks  
**Estimated:** 1–2 hours

---

## 2. PARALLELIZATION MATRIX

| Phase | Chunks | Can Run in Parallel |
|-------|--------|---------------------|
| Phase 1 | 1 | Chunk 1 only |
| Phase 2 | 2, 3, 4, 5, 6 | All 5 in parallel (after Chunk 1) |
| Phase 3 | 7, 8, 9 | 7 + 8 + 9 in parallel (after Phase 2) |
| Phase 4 | 10 | Chunk 10 (after Phase 3) |
| Phase 5 | 11 | Chunk 11 (optional) |

**Recommended agent launch order:**
1. Launch Agent A: Chunk 1
2. After Chunk 1 done: Launch Agents B, C, D, E, F for Chunks 2–6
3. After Chunks 2–6 done: Launch Agents G, H, I for Chunks 7, 8, 9
4. After Chunks 7–9 done: Launch Agent J for Chunk 10
5. Optional: Agent K for Chunk 11

---

## 3. GITHUB PUBLISHING WORKFLOW

### Repository Structure

```
audiobook-creator-v7/
├── .github/
│   └── workflows/
│       ├── ci.yml          # Lint + tests on PR
│       └── release.yml     # Optional: build artifacts
├── src/
│   ├── __init__.py
│   ├── manifest.py
│   ├── pipeline.py
│   ├── tts/
│   ├── parsers/
│   ├── detection/
│   ├── stages/
│   ├── cache.py
│   ├── pronunciation.py
│   ├── ffmpeg_utils.py
│   ├── ui.py
│   └── app.py
├── tests/
│   ├── test_manifest.py
│   ├── test_tts.py
│   ├── test_parsers.py
│   └── ...
├── web/                    # Vercel website (see Section 5)
│   ├── package.json
│   ├── next.config.js
│   └── ...
├── requirements.txt
├── requirements-dev.txt
├── README.md
├── IMPLEMENTATION_PLAN.md
├── audiobook_creator_v7.py  # Single-file build (optional)
└── audiobook_v7_handoff.md  # Copy of handoff
```

### Branch Strategy

- `main` — stable, deployable
- `develop` — integration branch for chunks
- `chunk/N` — e.g. `chunk/1-manifest`, `chunk/2-tts`, etc.

### PR Conventions

- PR title: `[Chunk N] Brief description`
- PR body: Link to handoff section, list of files changed
- Require: at least 1 approval if team, or self-merge for solo

### CI Pipeline (`.github/workflows/ci.yml`)

```yaml
name: CI
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - run: pip install -r requirements.txt -r requirements-dev.txt
      - run: python -m pytest tests/ -v
      - run: ruff check src/
```

---

## 4. IMPROVEMENTS TO THE HANDOFF

### 4.1 Add Error Recovery

- **Resume from crash:** Manifest already supports this; add `stage_generate()` logic to skip `status: cached` segments
- **Retry logic:** Wrap TTS calls in `tenacity` (3 retries, exponential backoff) for edge-tts network failures
- **Corrupt cache detection:** If `cache_file` exists but `ffprobe` fails, mark segment `status: error` and re-generate

### 4.2 Add Progress Persistence

- Store `progress.estimated_remaining_seconds` as running average of last N segments
- Add `progress.last_updated` for UI staleness detection

### 4.3 Add Validation

- Pydantic models for manifest schema — fail fast on invalid JSON
- Validate FFmpeg is installed and has required codecs before starting

### 4.4 Add Logging

- Structured logging (JSON) for debugging long runs
- Log segment index, voice, duration, cache hit/miss

### 4.5 Add Tests

- Sample EPUB/PDF/TXT in `tests/fixtures/` (small, public domain)
- Mock edge-tts and FFmpeg in unit tests
- Integration test: parse → generate 2 segments → assemble (minimal pipeline)

### 4.6 Add Configuration

- `config.yaml` or `.env` for cache size, concurrency, paths
- Override via environment variables for Docker/cloud

### 4.7 Add Docker Support

- `Dockerfile` for reproducible runs
- Useful for users without Python/FFmpeg installed locally

---

## 5. VERCEL WEBSITE (Landing Page)

**Goal:** Professional web presence. Gradio runs as a Python server and cannot run on Vercel directly. Use Vercel for a **landing page** that links to the app.

### Option A: Next.js Landing Page (Recommended)

Create `web/` directory:

```
web/
├── package.json
├── next.config.js
├── tailwind.config.js
├── app/
│   ├── layout.tsx
│   ├── page.tsx
│   └── globals.css
├── components/
│   ├── Hero.tsx
│   ├── Features.tsx
│   ├── HowItWorks.tsx
│   └── CTA.tsx
└── public/
    └── favicon.ico
```

**Content:**
- Hero: "Turn Any Book Into an Audiobook"
- Features: EPUB/PDF support, multiple voices, chapter detection, offline mode
- How it works: Parse → Generate → Assemble
- CTA: "Try it on Hugging Face" or "Run locally" (links to repo + Gradio Space)

**Deployment:**
1. Connect repo to [Vercel](https://vercel.com) (Import Git Repository)
2. Set **Root Directory** to `web` (Project Settings → General)
3. Deploy — Next.js is auto-detected
4. Or from CLI: `cd web && npx vercel`
5. Custom domain: add in Vercel project settings

### Option B: Gradio on Hugging Face Spaces + Vercel Landing

1. Deploy Gradio app to [Hugging Face Spaces](https://huggingface.co/spaces) (free, supports Gradio natively)
2. Vercel site links to: `https://huggingface.co/spaces/yourusername/audiobook-creator`

### Option C: Full-Stack on Vercel (Advanced)

- Next.js frontend with file upload
- Vercel Serverless Functions call external API (e.g. Modal, RunPod, or self-hosted) for TTS
- More complex, higher cost — only if you need everything on one domain

### Recommended: A + B

- **Vercel:** Beautiful landing page, docs, download instructions
- **Hugging Face Spaces:** Free Gradio hosting for "Try it now"

---

## 6. IMPLEMENTATION ORDER SUMMARY

| Step | Action |
|------|--------|
| 1 | Create repo structure, add `requirements.txt`, copy handoff |
| 2 | Launch Agent for Chunk 1 → PR → merge |
| 3 | Launch 5 agents for Chunks 2–6 in parallel → PRs → merge |
| 4 | Launch 3 agents for Chunks 7–9 in parallel → PRs → merge |
| 5 | Launch Agent for Chunk 10 → PR → merge |
| 6 | Add CI workflow, README, Dockerfile |
| 7 | Create `web/` Next.js landing page |
| 8 | Deploy web to Vercel, Gradio to Hugging Face Spaces |
| 9 | Update README with live links |

---

## 7. QUICK START FOR AGENTS

Each agent should receive:
1. This plan (`IMPLEMENTATION_PLAN.md`)
2. The handoff (`audiobook_v7_handoff.md`)
3. Specific chunk number and file list
4. Instruction: "Implement Chunk N. Create branch `chunk/N`. Submit PR when tests pass."

Example prompt for Agent on Chunk 2:
> Implement Chunk 2 (TTS Engine Abstraction) from IMPLEMENTATION_PLAN.md. Create `src/tts/base.py`, `src/tts/edge_tts.py`, `src/tts/kokoro.py`. Follow the handoff Section 2 exactly. Add a test in `tests/test_tts.py` that generates one segment with edge-tts. Branch: `chunk/2-tts`.
