// Split long text into TTS-friendly chunks that respect sentence and
// paragraph boundaries. Keeps each chunk under `maxChars` (default 2500).
// We prefer shorter chunks (~2k chars) because the Read Aloud API is
// both faster and more reliable on small inputs and it lets us run
// several requests in parallel.

const DEFAULT_MAX_CHARS = 2200;
const HARD_MAX = 7800; // server side is 8000

// Abbreviations whose trailing dot must not be treated as a sentence boundary.
const ABBREV_RE = /\b(Mr|Mrs|Ms|Dr|Prof|Sgt|Cpl|Lt|Capt|Gen|Col|Brig|Rev|Hon|St|Sr|Jr|vs|etc|viz|approx|dept|e\.g|i\.e|et al|Vol|No|pp|fig|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\./gi;
// U+2060 WORD JOINER — invisible, ignored by TTS, safe as a sentinel
const SENT_GUARD = "\u2060";

function protectAbbrevs(text) {
  return text.replace(ABBREV_RE, (m) => m.slice(0, -1) + SENT_GUARD);
}

function restoreAbbrevs(text) {
  return text.split(SENT_GUARD).join(".");
}

export function chunkText(rawText, maxChars = DEFAULT_MAX_CHARS) {
  const text = String(rawText || "").replace(/\r\n?/g, "\n").trim();
  if (!text) return [];

  const limit = Math.min(HARD_MAX, Math.max(400, Number(maxChars) || DEFAULT_MAX_CHARS));

  const paragraphs = text
    .split(/\n{2,}/)
    .map((p) => p.trim())
    .filter(Boolean);

  const chunks = [];
  let buffer = "";

  const flush = () => {
    const trimmed = buffer.trim();
    if (trimmed) chunks.push(trimmed);
    buffer = "";
  };

  const addSentence = (sentence) => {
    const next = buffer ? `${buffer} ${sentence}` : sentence;
    if (next.length <= limit) {
      buffer = next;
      return;
    }
    if (buffer) flush();
    if (sentence.length <= limit) {
      buffer = sentence;
    } else {
      // Fallback: hard-split very long sentences at word boundaries.
      let remaining = sentence;
      while (remaining.length > limit) {
        let cut = remaining.lastIndexOf(" ", limit);
        if (cut < Math.floor(limit * 0.5)) cut = limit;
        chunks.push(remaining.slice(0, cut).trim());
        remaining = remaining.slice(cut).trim();
      }
      buffer = remaining;
    }
  };

  for (const paragraph of paragraphs) {
    if (!paragraph) continue;
    // Paragraph break as natural breath point.
    if (buffer && buffer.length + paragraph.length + 1 > limit) flush();

    // Protect abbreviations so their dots don't look like sentence endings,
    // then split on . ! ? followed by whitespace, then restore.
    const guarded = protectAbbrevs(paragraph);
    const sentences = guarded.match(/[^.!?]+[.!?]+(?:['")\]\u2019\u201D]+)?|\S[^.!?]*$/g) || [guarded];
    for (const sentence of sentences) {
      addSentence(restoreAbbrevs(sentence.trim()));
    }
    // Force a paragraph break between paragraphs for clearer audio pacing.
    if (buffer && buffer.length > Math.floor(limit * 0.65)) flush();
  }
  flush();
  return chunks;
}

export function describeChunks(chunks) {
  const totalChars = chunks.reduce((sum, c) => sum + c.length, 0);
  return { count: chunks.length, totalChars };
}
