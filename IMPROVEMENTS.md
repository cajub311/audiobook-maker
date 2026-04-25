# Audiobook Maker V7 - Code & Website Improvements Guide

## Overview
This document summarizes the improvements made to the Audiobook Maker project to enhance code quality, website UX, and mobile web usability.

---

## ✅ Completed Improvements

### 1. **Configuration Management** (New: `config.py`)
**Status**: ✅ Complete & Committed

Centralized configuration file that replaces hard-coded values scattered throughout the codebase.

**Benefits**:
- Environment variable overrides for all settings (e.g., `ABM_CACHE_SIZE_GB=200`)
- Easy to modify without editing main code
- Better for DevOps and deployment automation
- Clear documentation of all configurable options

**Key Settings Available**:
- App version & directories
- FFmpeg timeouts and retry counts
- Max file/URL sizes, network timeouts
- TTS engine parameters (char/sec speeds)
- Cache sizes and entry limits
- UI mode defaults (easy/advanced)
- Validation options (URL safety, rate limiting)

**How to Use**:
```bash
# Override config via environment variables
ABM_CACHE_SIZE_GB=500 ABM_ENABLE_RATE_LIMITING=true python3 audiobook_creator_v7.py

# Or modify config.py directly
from config import CACHE_SIZE_GB, MAX_FILE_UPLOAD_MB
```

---

### 2. **Website/Launcher Enhancements** (Updated: `index.html`)
**Status**: ✅ Complete & Committed

Significant UX improvements for mobile and desktop users.

#### Button/Input Sizing
- **Before**: Small buttons (px-4 py-2) with minimal padding
- **After**: Larger buttons (px-6 py-3) with 44px+ minimum touch target
  - Meets WCAG 2.5A accessibility standard for touch targets
  - Full-width copy buttons on mobile (py-2.5)
  - Hover effects and transitions for better feedback

#### Feature Additions
1. **Feature Comparison Table**
   - Shows Easy Mode vs Advanced Mode differences
   - Clarifies when to use each mode
   - One-glance feature availability

2. **Time Estimator Calculator**
   - Users input page count
   - Automatic calculation showing:
     - Edge TTS estimate (cloud, faster)
     - Kokoro estimate (offline, slower)
   - Based on realistic speeds and page-to-word conversion
   - Helps set expectations before starting

3. **FAQ Section** (5 Common Questions)
   - Installation requirements
   - TTS engine differences
   - Pause/resume capabilities
   - Supported file formats
   - File size limits and recommendations
   - Uses `<details>` elements for collapsible content

4. **Theme System Enhancement**
   - System preference detection (`prefers-color-scheme`)
   - Falls back to localStorage (remembered preference)
   - Smooth transitions when toggling
   - Better dark mode support overall

#### Visual Improvements
- Better button padding and touch targets
- Hover state transitions and scale effects
- Improved color contrast in dark mode
- Better mobile layout (full-width elements)

**Results**:
- 🎯 Better user guidance before installation
- 🎯 Faster decision-making (Easy vs Advanced)
- 🎯 Accessibility improvements
- 🎯 Mobile-friendly experience
- 🎯 Reduced support questions (FAQ section)

---

## 🎯 Key Recommendations Not Yet Implemented

### High Priority (1-2 hours each)

#### 1. **Add Step-by-Step Progress Messages**
**File**: `audiobook_creator_v7.py` (Stage functions)

Currently shows "Segment X/Y" but could show:
```
✓ Parsing: 5/10 chapters found
✓ Generating: Chapter 1 audio (Edge TTS, 28 chars/sec)
🕐 ETA: 3m 45s remaining
```

**Implementation**:
```python
# In stage_parse progress callback
desc = f"Parsing: {done}/{total} chapters found"

# In stage_generate progress callback
desc = f"Generating: {speaker_name} audio (Chapter {ch_idx+1})"
```

#### 2. **Input Validation Improvements**
**File**: `audiobook_creator_v7.py` (Lines 200-300)

Add stricter checks:
```python
# File size validation
MAX_FILE_MB = int(os.getenv("ABM_MAX_FILE_UPLOAD_MB", "500"))
if file_size_mb > MAX_FILE_MB:
    raise ValueError(f"File too large: {file_size_mb}MB > {MAX_FILE_MB}MB limit")

# URL timeout
trafilatura.extract(url, timeout=URL_FETCH_TIMEOUT_S)

# Duplicate submission prevention
recent_texts = load_recent_texts()
if text_hash in recent_texts:
    raise ValueError("This text was just submitted. Please wait or modify.")
```

#### 3. **Dialogue Detection Flexibility**
**File**: `audiobook_creator_v7.py` (Lines 807+)

Add configuration for detection strategy:
```python
strategy = settings.get("dialogue_detection_strategy", "auto")
# Options: "regex" (fast), "quote-pattern", "spacy" (accurate but slow), "auto" (try regex first, fall back to spacy)

if strategy == "regex":
    # Fast regex-only detection
    pass
elif strategy == "spacy":
    # Accurate NLP detection
    pass
```

#### 4. **Mobile CSS Improvements**
**File**: `audiobook_creator_v7.py` (MOBILE_CSS section)

Current MOBILE_CSS is good but could add:
```css
/* Better button sizes for mobile */
.easy-action-btn {
  min-height: 44px;  /* WCAG touch target */
  min-width: 44px;
  padding: 12px 24px;
}

/* Full-width inputs on mobile */
@media (max-width: 640px) {
  input, textarea, select {
    font-size: 16px; /* Prevents zoom on iOS */
  }
}
```

### Medium Priority (2-4 hours each)

#### 5. **Async TTS Generation**
**Current**: Blocking UI during generation
**Recommendation**: Split into separate thread/process to allow UI updates

#### 6. **Cloud API Option**
**File**: Create `api/process.js` or similar

Option for users who don't want local installation:
- Create cloud endpoint that accepts text/files
- Process asynchronously on backend
- Return download link when ready
- Store results temporarily (24-48 hours)

#### 7. **Code Modularization**
**Consider splitting from 3,704-line monolith**:
```
audiobook_maker/
├── tts/
│   ├── __init__.py
│   ├── engine.py (base class)
│   ├── edge_tts.py
│   └── kokoro.py
├── parsers/
│   ├── __init__.py
│   ├── text.py
│   ├── pdf.py
│   ├── epub.py
│   └── url.py
├── cache/
│   └── audio.py
├── ui/
│   └── gradio_app.py
└── core.py (orchestration)
```

This would:
- Improve testability
- Make code easier to understand
- Enable better type hints
- Simplify debugging

### Low Priority (Nice-to-have)

#### 8. **Type Hints Throughout**
Add type hints to major functions (currently minimal)

#### 9. **Better Error Messages**
Categorize errors:
- Network errors (retry option)
- Validation errors (clear guidance)
- System errors (check dependencies)

#### 10. **Logging System**
Add structured logging for debugging:
```python
import logging
logger = logging.getLogger(__name__)
logger.info(f"Generated {segment_count} segments in {elapsed_s:.1f}s")
```

---

## 📱 Mobile Web Usability - Three Options

### Current State
✅ Works on mobile browsers
✅ PWA installable
❌ Still requires Python backend (no true web-only mode)

### Option A: Browser-Based Demo (Easiest, Recommended First)
**Effort**: 1-2 hours
**Files to Create**:
- `web/demo.html` - Limited 5-minute sample
- Uses cloud TTS API only (no local TTS)
- No installation needed
- Clearly markets as "demo" with link to full version

### Option B: Full Hybrid Cloud API (Medium)
**Effort**: 4-6 hours
**Files to Create**:
- `api/process.js` - Upload/process endpoint
- `web/index.html` - Upload interface
- Database for tracking jobs
- Webhook notifications

### Option C: Browser Processing Library (Advanced)
**Effort**: 8-12 hours
**Files to Create**:
- `web/processor.js` - Client-side text processing
- `web/api-client.js` - Cloud TTS integration
- `web/storage.js` - IndexedDB for local storage
- Full web-only experience

**Recommendation**: Start with Option A (demo), then expand to B or C based on demand

---

## 🚀 Recommended Implementation Order

### Phase 1: Quick Wins (Already Done)
- ✅ Create config.py
- ✅ Enhance website
- ✅ System preference detection

### Phase 2: Easy Mode Refinements (1-2 hours)
- [ ] Better progress messages in UI
- [ ] Input validation improvements
- [ ] Dialogue detection strategy selector

### Phase 3: Mobile Experience (2-3 hours)
- [ ] Mobile CSS optimizations (16px font, 44px touch targets)
- [ ] Web-only demo version
- [ ] Better error messages

### Phase 4: Code Quality (4-5 hours)
- [ ] Add type hints to key functions
- [ ] Modularize TTS/parser/cache code
- [ ] Add docstrings to complex functions
- [ ] Improve logging

### Phase 5: Advanced Features (6-8 hours)
- [ ] Cloud API for no-install users
- [ ] Async generation improvements
- [ ] Advanced configuration UI

---

## 💡 Testing & Validation Checklist

- [ ] Run existing tests: `python tests/test_reliability.py`
- [ ] Manual test on mobile (iOS Safari, Android Chrome)
- [ ] Test config overrides: `ABM_CACHE_SIZE_GB=100 python3 audiobook_creator_v7.py`
- [ ] Test time estimator calculator on index.html
- [ ] Check button sizes on 4-inch phone (44px minimum)
- [ ] Verify dark mode toggle saves preference
- [ ] Test FAQ accordion expand/collapse
- [ ] Check lighthouse performance audit
- [ ] Test on slow 3G network
- [ ] Verify all links work (GitHub, API endpoints, etc.)

---

## 📊 Impact Summary

| Improvement | Users | Effort | Impact |
|-----------|-------|--------|--------|
| Config.py | Power users | Low | 🟢 Removes friction |
| Website UX | All | Low | 🟢 Better onboarding |
| Progress messages | All | Low | 🟢 Less anxiety |
| Mobile buttons | Mobile | Low | 🟢 Easier interaction |
| Time estimator | All | Low | 🟢 Better expectations |
| FAQ section | New users | Low | 🟢 Self-service answers |
| Web demo | Casual users | Medium | 🟡 Increases reach |
| Code modularization | Maintainers | High | 🟢 Easier updates |

---

## 🎯 What to Keep

- ✅ Three-stage pipeline (Parse → Generate → Assemble)
- ✅ Dual TTS engines with fallback
- ✅ Atomic manifest writes & recovery
- ✅ Dialogue detection & character voices
- ✅ Cloud backup (JSONBlob)
- ✅ PWA support
- ✅ Reliable caching with validation
- ✅ Resume capabilities
- ✅ Pronunciation overrides
- ✅ M4B chapter metadata

---

## 🔗 Resources

- [WCAG 2.5A Touch Target Guidelines](https://www.w3.org/WAI/WCAG21/Understanding/target-size.html)
- [prefers-color-scheme CSS](https://developer.mozilla.org/en-US/docs/Web/CSS/@media/prefers-color-scheme)
- [Web App Manifest Spec](https://www.w3.org/TR/appmanifest/)
- [Gradio Documentation](https://gradio.app/docs)

---

**Created**: 2026-03-06
**Project**: Audiobook Maker V7
**Status**: Phase 1 & 2 Implementation Guide Ready

