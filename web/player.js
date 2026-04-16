// In-browser audiobook player engine.
// - Splits text into chapters then sentence-level segments so SpeechSynthesisUtterance
//   playback is reliable on Chrome/Safari (long utterances get truncated on some engines).
// - Publishes progress and boundary events so the UI can show chapter, sentence, and
//   word-level highlighting plus seek to a specific chapter/sentence.

const CHAPTER_REGEX = /(^|\n)\s*(chapter|part|book|prologue|epilogue)[^\n]*/gi;

export function splitChapters(rawText) {
  const text = String(rawText || "").replace(/\r\n/g, "\n").trim();
  if (!text) return [];

  const matches = [];
  let m;
  CHAPTER_REGEX.lastIndex = 0;
  while ((m = CHAPTER_REGEX.exec(text)) !== null) {
    matches.push({ index: m.index + (m[1] ? m[1].length : 0), title: m[0].trim() });
  }

  if (matches.length === 0) {
    // Fall back to splitting on big blank-line separators ("===" / 3+ blank lines).
    const parts = text.split(/\n{3,}|\n=+\n/).filter((seg) => seg.trim().length > 0);
    return parts.map((body, i) => ({
      title: parts.length > 1 ? `Section ${i + 1}` : "Audiobook",
      body: body.trim(),
    }));
  }

  const chapters = [];
  const preamble = text.slice(0, matches[0].index).trim();
  if (preamble) {
    chapters.push({ title: "Intro", body: preamble });
  }
  for (let i = 0; i < matches.length; i += 1) {
    const start = matches[i].index;
    const end = i + 1 < matches.length ? matches[i + 1].index : text.length;
    const body = text.slice(start, end).trim();
    if (!body) continue;
    const firstLineEnd = body.indexOf("\n");
    const title = (firstLineEnd === -1 ? body : body.slice(0, firstLineEnd)).trim();
    chapters.push({
      title: title.length > 80 ? title.slice(0, 77) + "…" : title,
      body,
    });
  }
  return chapters;
}

export function splitSentences(body) {
  const clean = String(body || "").replace(/\s+/g, " ").trim();
  if (!clean) return [];
  // Split on sentence punctuation while keeping the terminator.
  const parts = clean.match(/[^.!?\u2026]+[.!?\u2026]+[\"')\]]*\s*|[^.!?\u2026]+$/g) || [clean];
  // Merge overly short fragments (e.g. "Mr.") back onto the next sentence.
  const merged = [];
  for (const piece of parts) {
    const trimmed = piece.trim();
    if (!trimmed) continue;
    if (merged.length && (merged[merged.length - 1].length < 12 || /\b(Mr|Mrs|Dr|Ms|St|Jr|Sr|vs|No|e\.g|i\.e)\.$/i.test(merged[merged.length - 1]))) {
      merged[merged.length - 1] = `${merged[merged.length - 1]} ${trimmed}`;
    } else {
      merged.push(trimmed);
    }
  }
  // Hard cap per utterance: some engines choke past ~300 chars.
  const capped = [];
  for (const sentence of merged) {
    if (sentence.length <= 280) {
      capped.push(sentence);
      continue;
    }
    let remaining = sentence;
    while (remaining.length > 280) {
      const cutAt = remaining.lastIndexOf(" ", 260);
      const cut = cutAt > 160 ? cutAt : 260;
      capped.push(remaining.slice(0, cut).trim());
      remaining = remaining.slice(cut).trim();
    }
    if (remaining) capped.push(remaining);
  }
  return capped;
}

export function buildAudiobook(rawText) {
  const chapters = splitChapters(rawText).map((ch, chIdx) => {
    const sentences = splitSentences(ch.body);
    return {
      index: chIdx,
      title: ch.title,
      sentences,
      charCount: sentences.reduce((sum, s) => sum + s.length, 0),
    };
  }).filter((ch) => ch.sentences.length > 0);

  const totalChars = chapters.reduce((sum, ch) => sum + ch.charCount, 0);
  const totalSentences = chapters.reduce((sum, ch) => sum + ch.sentences.length, 0);
  return {
    chapters,
    totalChars,
    totalSentences,
    estimatedSeconds: Math.max(1, Math.round(totalChars / 16)), // ~16 cps offline synth
  };
}

export class AudiobookPlayer extends EventTarget {
  constructor() {
    super();
    this.book = null;
    this.chapterIndex = 0;
    this.sentenceIndex = 0;
    this.currentUtterance = null;
    this.playing = false;
    this.paused = false;
    this.rate = 1.0;
    this.pitch = 1.0;
    this.volume = 1.0;
    this.voiceURI = null;
    this._synth = typeof window !== "undefined" ? window.speechSynthesis : null;
    this._boundaryChars = 0;
    this._advanceRequested = false;
  }

  load(rawText) {
    this.stop();
    this.book = buildAudiobook(rawText);
    this.chapterIndex = 0;
    this.sentenceIndex = 0;
    this._emit("loaded", { book: this.book });
    return this.book;
  }

  setVoice(voiceURI) { this.voiceURI = voiceURI || null; }
  setRate(rate) { this.rate = Math.min(2.5, Math.max(0.3, Number(rate) || 1)); }
  setPitch(pitch) { this.pitch = Math.min(2, Math.max(0, Number(pitch) || 1)); }
  setVolume(volume) { this.volume = Math.min(1, Math.max(0, Number(volume) || 1)); }

  jumpToChapter(ci) {
    if (!this.book || !this.book.chapters[ci]) return;
    const wasPlaying = this.playing;
    this._cancelSpeech();
    this.chapterIndex = ci;
    this.sentenceIndex = 0;
    this._emit("position", this._positionSnapshot());
    if (wasPlaying) this.play();
  }

  jumpToSentence(ci, si) {
    if (!this.book || !this.book.chapters[ci]) return;
    const wasPlaying = this.playing;
    this._cancelSpeech();
    this.chapterIndex = ci;
    this.sentenceIndex = Math.max(0, Math.min(this.book.chapters[ci].sentences.length - 1, si));
    this._emit("position", this._positionSnapshot());
    if (wasPlaying) this.play();
  }

  nextSentence() {
    if (!this.book) return;
    const ch = this.book.chapters[this.chapterIndex];
    if (!ch) return;
    if (this.sentenceIndex + 1 < ch.sentences.length) {
      this.jumpToSentence(this.chapterIndex, this.sentenceIndex + 1);
    } else if (this.chapterIndex + 1 < this.book.chapters.length) {
      this.jumpToChapter(this.chapterIndex + 1);
    }
  }

  prevSentence() {
    if (!this.book) return;
    if (this.sentenceIndex > 0) {
      this.jumpToSentence(this.chapterIndex, this.sentenceIndex - 1);
      return;
    }
    if (this.chapterIndex > 0) {
      const prev = this.book.chapters[this.chapterIndex - 1];
      this.jumpToSentence(this.chapterIndex - 1, prev.sentences.length - 1);
    }
  }

  play() {
    if (!this.book || !this._synth) {
      this._emit("error", { message: "No audiobook loaded or speech synthesis unavailable." });
      return;
    }
    if (this.paused && this.currentUtterance) {
      this._synth.resume();
      this.paused = false;
      this.playing = true;
      this._emit("state", this._stateSnapshot());
      return;
    }
    this._speakCurrent();
  }

  pause() {
    if (this._synth && this.playing && !this.paused) {
      this._synth.pause();
      this.paused = true;
      this.playing = false;
      this._emit("state", this._stateSnapshot());
    }
  }

  stop() {
    this._cancelSpeech();
    this.playing = false;
    this.paused = false;
    this._emit("state", this._stateSnapshot());
  }

  getPosition() { return this._positionSnapshot(); }
  getState() { return this._stateSnapshot(); }

  _cancelSpeech() {
    if (!this._synth) return;
    this._advanceRequested = false;
    try { this._synth.cancel(); } catch (_err) {}
    this.currentUtterance = null;
    this._boundaryChars = 0;
  }

  _speakCurrent() {
    if (!this.book || !this._synth) return;
    const ch = this.book.chapters[this.chapterIndex];
    if (!ch) {
      this.stop();
      this._emit("ended", {});
      return;
    }
    const sentence = ch.sentences[this.sentenceIndex];
    if (!sentence) {
      this.nextSentence();
      if (this.book.chapters[this.chapterIndex]) this._speakCurrent();
      return;
    }

    const utterance = new SpeechSynthesisUtterance(sentence);
    utterance.rate = this.rate;
    utterance.pitch = this.pitch;
    utterance.volume = this.volume;
    if (this.voiceURI) {
      const voice = (this._synth.getVoices() || []).find((v) => v.voiceURI === this.voiceURI);
      if (voice) utterance.voice = voice;
    }
    utterance.onstart = () => {
      this.playing = true;
      this.paused = false;
      this._boundaryChars = 0;
      this._emit("state", this._stateSnapshot());
      this._emit("sentenceStart", { chapterIndex: this.chapterIndex, sentenceIndex: this.sentenceIndex, text: sentence });
    };
    utterance.onboundary = (event) => {
      if (event.name !== "word") return;
      this._boundaryChars = event.charIndex || 0;
      this._emit("word", {
        chapterIndex: this.chapterIndex,
        sentenceIndex: this.sentenceIndex,
        charIndex: event.charIndex || 0,
        text: sentence,
      });
    };
    utterance.onend = () => {
      if (this._advanceRequested) return;
      const ch2 = this.book.chapters[this.chapterIndex];
      if (!ch2) { this.stop(); this._emit("ended", {}); return; }
      if (this.sentenceIndex + 1 < ch2.sentences.length) {
        this.sentenceIndex += 1;
        this._emit("position", this._positionSnapshot());
        this._speakCurrent();
      } else if (this.chapterIndex + 1 < this.book.chapters.length) {
        this.chapterIndex += 1;
        this.sentenceIndex = 0;
        this._emit("chapterChange", { chapterIndex: this.chapterIndex });
        this._emit("position", this._positionSnapshot());
        this._speakCurrent();
      } else {
        this.playing = false;
        this._emit("state", this._stateSnapshot());
        this._emit("ended", {});
      }
    };
    utterance.onerror = (event) => {
      // "interrupted" and "canceled" are expected when we seek or stop.
      if (event.error === "interrupted" || event.error === "canceled") return;
      this.playing = false;
      this._emit("error", { message: event.error || "Speech synthesis error", chapterIndex: this.chapterIndex, sentenceIndex: this.sentenceIndex });
      this._emit("state", this._stateSnapshot());
    };

    this.currentUtterance = utterance;
    this._advanceRequested = false;
    try { this._synth.cancel(); } catch (_err) {}
    this._synth.speak(utterance);
    this.playing = true;
    this.paused = false;
    this._emit("state", this._stateSnapshot());
  }

  _positionSnapshot() {
    if (!this.book) return null;
    let charsPlayed = 0;
    for (let i = 0; i < this.chapterIndex; i += 1) charsPlayed += this.book.chapters[i].charCount;
    const ch = this.book.chapters[this.chapterIndex];
    if (ch) {
      for (let j = 0; j < this.sentenceIndex; j += 1) charsPlayed += ch.sentences[j].length;
      charsPlayed += this._boundaryChars || 0;
    }
    const progress = this.book.totalChars ? charsPlayed / this.book.totalChars : 0;
    return {
      chapterIndex: this.chapterIndex,
      sentenceIndex: this.sentenceIndex,
      totalChapters: this.book.chapters.length,
      progress: Math.min(1, progress),
      charsPlayed,
      totalChars: this.book.totalChars,
    };
  }

  _stateSnapshot() {
    return {
      playing: this.playing,
      paused: this.paused,
      hasBook: !!this.book,
      rate: this.rate,
      pitch: this.pitch,
      volume: this.volume,
      voiceURI: this.voiceURI,
    };
  }

  _emit(type, detail) {
    this.dispatchEvent(new CustomEvent(type, { detail }));
  }
}

export const __test__ = { CHAPTER_REGEX };
