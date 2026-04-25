// Text utilities for the audiobook maker:
// - chapter splitter (Chapter / Part / Book / Section heuristics)
// - dialogue detection using smart and straight quotes plus guillemets
// - speaker attribution via surrounding speech verbs
//
// Exposes a pure JS API that works in the browser and under Node for tests.

const CHAPTER_REGEX = /^\s*(?:chapter|part|book|section)\s+[ivxlcdm0-9]+[:.\s-]*.*$/im;

export function escapeHtml(value) {
  return String(value || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

export function normalizeText(raw) {
  return String(raw || "")
    .replace(/\r\n?/g, "\n")
    .replace(/\u00a0/g, " ")
    .replace(/[ \t]+\n/g, "\n")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

export function splitChapters(raw) {
  const text = normalizeText(raw);
  if (!text) return [];
  const lines = text.split("\n");
  const chapters = [];
  let current = { title: "Prologue", lines: [] };
  for (const line of lines) {
    const stripped = line.trim();
    if (stripped && stripped.length <= 120 && CHAPTER_REGEX.test(stripped)) {
      if (current.lines.length) {
        chapters.push({ title: current.title, text: current.lines.join("\n").trim() });
      }
      current = { title: stripped, lines: [] };
    } else {
      current.lines.push(line);
    }
  }
  if (current.lines.length) {
    chapters.push({ title: current.title, text: current.lines.join("\n").trim() });
  }
  if (chapters.length === 1 && chapters[0].title === "Prologue") {
    chapters[0].title = "Chapter 1";
  }
  return chapters.filter((c) => c.text);
}

const SPEAKER_VERBS = [
  "said", "says", "replied", "whispered", "asked", "shouted", "muttered", "answered",
  "cried", "sighed", "laughed", "called", "yelled", "gasped", "exclaimed", "murmured",
  "added", "continued", "declared", "demanded", "insisted", "responded", "hissed",
  "stammered", "snapped", "growled", "barked", "groaned", "mumbled", "chuckled",
  "noted", "remarked", "scoffed", "interrupted", "began", "confessed",
  "offered", "pleaded", "warned", "urged", "teased", "scolded", "pressed", "prodded",
  "shot back", "called out", "spoke up", "went on", "went on to say", "repeated",
  "breathed",
];
const SPEAKER_VERB_SRC = SPEAKER_VERBS.join("|");
const NAME_SRC = "[A-Z][a-zA-Z'\\-]{1,24}(?:\\s+[A-Z][a-zA-Z'\\-]{1,24})?";
const BEFORE_REGEX = new RegExp(`(${NAME_SRC})\\s+(?:${SPEAKER_VERB_SRC})\\b`);
const AFTER_REGEX = new RegExp(`\\b(?:${SPEAKER_VERB_SRC})\\s+(${NAME_SRC})`);
const DIALOGUE_REGEX =
  /(?:[\u201C]([^\u201D]+)[\u201D]|"([^"\n]{1,500})"|[\u00AB]([^\u00BB]+)[\u00BB])/g;
const PRONOUN_BLOCKLIST = new Set([
  "He", "She", "They", "We", "I", "It", "You", "One", "Someone", "Anyone",
  "Everyone", "Nobody", "The", "A", "An", "Then", "But", "And", "So", "Yet",
  "Now", "Here", "There", "This", "That", "These", "Those", "Mr", "Mrs", "Ms",
  "Dr", "Sir", "Madam", "Voice", "Man", "Woman", "Boy", "Girl", "Child", "Both",
  "Either", "Neither", "None", "Something", "Somewhere",
]);

/** Hints for mapping "she"/"he" when only one name in each group appears in recent context */
const FEMALE_NAME_HINTS = new Set([
  "Sarah", "Alice", "Emma", "Mary", "Anna", "Laura", "Clara", "Elena", "Maria", "Rachel",
  "Jennifer", "Jessica", "Lisa", "Karen", "Susan", "Helen", "Julia", "Kate", "Amy", "Diana",
]);
const MALE_NAME_HINTS = new Set([
  "Mark", "John", "Bob", "Tom", "David", "James", "Paul", "Chris", "Daniel", "Michael",
  "Robert", "William", "Marcus", "Luke", "Brian", "Kevin", "Jason", "Eric", "Frank", "George",
]);

const CAST_NAME_SKIP = new Set([
  "The", "But", "And", "Yet", "For", "Nor", "His", "Her", "She", "They", "This", "That",
  "There", "Then", "What", "When", "Where", "Which", "While", "With", "From", "Into", "Upon",
  "After", "Before", "During", "Every", "Some", "Most", "Many", "Such", "Even", "Only",
  "Just", "Like", "Each", "Both", "Either", "Neither", "Someone", "Everyone", "Nobody",
  "Something", "Nothing", "Grief", "Phone", "Screen", "Voice", "Night", "Morning", "Evening",
  "Basement", "Bedroom", "House", "Floor", "Door", "Light", "Dark", "Oak", "Cemetery",
]);

function cleanSpeakerName(raw) {
  if (!raw) return null;
  const trimmed = String(raw).trim().replace(/[.,;:!?\u2014\u2013-]+$/, "");
  const first = trimmed.split(/\s+/)[0];
  if (!first || first.length < 2) return null;
  if (PRONOUN_BLOCKLIST.has(first)) return null;
  return trimmed;
}

function firstToken(name) {
  return String(name || "").trim().split(/\s+/)[0] || "";
}

function genderGuess(name) {
  const t = firstToken(name);
  if (FEMALE_NAME_HINTS.has(t)) return "f";
  if (MALE_NAME_HINTS.has(t)) return "m";
  return null;
}

/** Ordered cast names (first appearance) from speech tags, *italics*, and "First Last" + common narration verbs */
export function extractCastOrdered(text) {
  const raw = String(text || "");
  const order = [];
  const seen = new Set();
  const add = (n) => {
    const c = cleanSpeakerName(n);
    if (!c) return;
    const tok = firstToken(c);
    if (CAST_NAME_SKIP.has(tok) || tok.length < 2) return;
    if (seen.has(tok)) return;
    seen.add(tok);
    order.push(c.split(/\s+/).length > 1 ? c : tok);
  };

  const nameVerb = new RegExp(`\\b(${NAME_SRC})\\s+(?:${SPEAKER_VERB_SRC})\\b`, "g");
  let m;
  while ((m = nameVerb.exec(raw)) !== null) {
    add(m[1]);
  }

  const firstLastVerb =
    /\b([A-Z][a-zA-Z'’\-]{1,22})\s+([A-Z][a-zA-Z'’\-]{1,22})\s+(?:had|has|was|were|stood|felt|walked|turned|picked|heard|remembered|laughed|cried|stopped|never|opened|closed|moved|sat|stared|whispered|started|lay)\b/g;
  while ((m = firstLastVerb.exec(raw)) !== null) {
    add(`${m[1]} ${m[2]}`);
  }

  const starName = /\*+\s*([A-Z][a-zA-Z'’\-]{2,20})\b/g;
  while ((m = starName.exec(raw)) !== null) {
    add(m[1]);
  }

  // Single name OR "First Last" + motion verb (avoid matching "Thompson" from "Mark Thompson walked").
  const nameNarrativeVerb =
    /\b([A-Z][a-zA-Z'’\-]{1,22}(?:\s+[A-Z][a-zA-Z'’\-]{1,22})?)\s+(?:walked|waited|stopped|stood|sat|turned|frowned|smiled|looked|sighed|nodded|thought|remembered|felt|trembled|shivered|blinked|gasped|winced|grimaced|paced|leaned|knelt|rose|entered|left|opened|closed|watched|stared|listened)\b/g;
  while ((m = nameNarrativeVerb.exec(raw)) !== null) {
    add(m[1]);
  }

  return order.slice(0, 12);
}

function lastMentionedCastMember(beforeSt, castOrder) {
  if (!castOrder.length) return null;
  const hay = String(beforeSt || "");
  let best = null;
  let bestIdx = -1;
  for (const name of castOrder) {
    const tok = firstToken(name);
    const re = new RegExp(`\\b${tok.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}\\b`);
    let idx = 0;
    while (true) {
      const found = hay.slice(idx).search(re);
      if (found < 0) break;
      idx += found;
      if (idx > bestIdx) {
        bestIdx = idx;
        best = name;
      }
      idx += 1;
    }
  }
  return best;
}

function resolvePronounSpeaker(beforeSt, pronoun, castOrder) {
  const p = String(pronoun || "").toLowerCase();
  const last = lastMentionedCastMember(beforeSt, castOrder);
  const lastG = last ? genderGuess(last) : null;
  if (p === "they") {
    return castOrder.find((n) => n !== last) || castOrder[0] || null;
  }
  if (p === "she") {
    const f = castOrder.filter((n) => genderGuess(n) === "f");
    if (f.length === 1) return f[0];
    const pick = f.find((n) => n !== last) || f[0];
    if (pick) return pick;
    if (lastG === "m") return castOrder.find((n) => genderGuess(n) === "f") || castOrder[1] || null;
    return castOrder.find((n) => genderGuess(n) === "f") || null;
  }
  if (p === "he") {
    const m = castOrder.filter((n) => genderGuess(n) === "m");
    if (m.length === 1) return m[0];
    const pick = m.find((n) => n !== last) || m[0];
    if (pick) return pick;
    if (lastG === "f") return castOrder.find((n) => genderGuess(n) === "m") || castOrder[0] || null;
    return castOrder.find((n) => genderGuess(n) === "m") || null;
  }
  return null;
}

function detectPronounSpeakerBefore(beforeRaw, castOrder) {
  const s = stripTrailingSpeechAttribution(String(beforeRaw || "")).trim();
  const m = s.match(new RegExp(`\\b(She|He|They)\\s+(?:${SPEAKER_VERB_SRC})\\b[^.!?]*$`, "i"));
  if (!m || !castOrder.length) return null;
  return resolvePronounSpeaker(s, m[1], castOrder);
}

/** `"I'm here," she said` — pronoun is right after the closing quote */
function detectPronounSpeakerAfter(beforeForContext, afterRaw, castOrder) {
  const s = String(afterRaw || "");
  const m = s.match(new RegExp(`^\\s*,?\\s*(she|he|they)\\s+(?:${SPEAKER_VERB_SRC})\\b`, "i"));
  if (!m || !castOrder.length) return null;
  const ctx = stripTrailingSpeechAttribution(String(beforeForContext || ""));
  return resolvePronounSpeaker(ctx, m[1], castOrder);
}

/** "Mark?" / "Sarah?" — addressee is named; speaker is the other principal */
function detectNameQuestionOtherSpeaker(quote, castOrder) {
  const q = String(quote || "").trim();
  const m = q.match(/^([A-Z][a-zA-Z'’\-]{2,20})\?$/);
  if (!m || castOrder.length < 2) return null;
  const askedTok = firstToken(cleanSpeakerName(m[1]) || "");
  if (!askedTok) return null;
  if (!castOrder.some((n) => firstToken(n) === askedTok)) return null;
  return castOrder.find((n) => firstToken(n) !== askedTok) || null;
}

/** Enough for `"…" she said. "Next line"` on prior lines without truncating the tag */
const CONTEXT_CHARS = 520;

/** "Sarah:" or "Mary Ann:" immediately before an opening quote */
function detectColonSpeakerBefore(beforeRaw) {
  const before = String(beforeRaw || "").replace(/\s+$/, "");
  const m = before.match(
    /(?:^|[.!?\n\u2026])\s*([A-Z][a-zA-Z'’\-]{1,24}(?:\s+[A-Z][a-zA-Z'’\-]{1,24})?)\s*:\s*$/,
  );
  if (!m) return null;
  return cleanSpeakerName(m[1]);
}

/** "…" — Sarah / - Sarah / (Sarah) right after the closing quote */
function detectTailSpeakerAfter(afterRaw) {
  const after = String(afterRaw || "");
  /** "Bob answered." / "Mary whispered" right after the closing quote */
  const nameVerb = after.match(
    new RegExp(`^\\s*(${NAME_SRC})\\s+(?:${SPEAKER_VERB_SRC})\\b`),
  );
  if (nameVerb) {
    const n = cleanSpeakerName(nameVerb[1]);
    if (n) return n;
  }
  const dash = after.match(
    /^\s*[—–\-]\s*([A-Z][a-zA-Z'’\-]{1,24}(?:\s+[A-Z][a-zA-Z'’\-]{1,24})?)\b/,
  );
  if (dash) {
    const n = cleanSpeakerName(dash[1]);
    if (n) return n;
  }
  const paren = after.match(
    /^\s*\(\s*([A-Z][a-zA-Z'’\-]{1,24}(?:\s+[A-Z][a-zA-Z'’\-]{1,24})?)\s*\)/,
  );
  if (paren) {
    const n = cleanSpeakerName(paren[1]);
    if (n) return n;
  }
  return null;
}

/** Name alone on the line before the paragraph continues into a quote */
function detectNameLineBeforeQuote(beforeRaw) {
  const before = String(beforeRaw || "").replace(/\s+$/, "");
  const m = before.match(/\n\s*([A-Z][a-zA-Z'’\-]{1,24}(?:\s+[A-Z][a-zA-Z'’\-]{1,24})?)\s*$/);
  if (!m) return null;
  return cleanSpeakerName(m[1]);
}

/** Strip trailing " Alice said." so the next quote is not attributed to the previous speaker. */
function stripTrailingSpeechAttribution(beforeRaw) {
  let s = String(beforeRaw || "");
  // Case-sensitive name: with /i, [A-Z] matches lowercase and "she said" was wrongly stripped as "She said".
  const tailRe = new RegExp(
    `\\s+(${NAME_SRC})\\s+(?:${SPEAKER_VERB_SRC})[.!?…]?\\s*$`,
  );
  for (let i = 0; i < 6; i += 1) {
    const m = s.match(tailRe);
    if (!m) break;
    s = s.slice(0, -m[0].length);
  }
  return s;
}

/** `"…" she said. "Next"` — next quote's speaker is the pronoun + speech verb at end of `before` */
function detectPronounSpeechTagBeforeQuote(beforeRaw, castOrder) {
  if (!castOrder.length) return null;
  const s = stripTrailingSpeechAttribution(String(beforeRaw || "")).trim();
  // No multiline flag: with /m, $ matches end-of-line and fails when "she said." is followed by \n before the next quote.
  const m = s.match(new RegExp(`(she|he|they)\\s+(?:${SPEAKER_VERB_SRC})\\b[.!?,…]?\\s*$`, "i"));
  if (!m) return null;
  return resolvePronounSpeaker(s, m[1], castOrder);
}

function detectSpeakerFromContext(before, after) {
  const beforeSt = stripTrailingSpeechAttribution(before);
  const scope = `${beforeSt} ${after || ""}`;
  const before_ = scope.match(BEFORE_REGEX);
  if (before_) {
    const name = cleanSpeakerName(before_[1]);
    if (name) return name;
  }
  const after_ = scope.match(AFTER_REGEX);
  if (after_) {
    const name = cleanSpeakerName(after_[1]);
    if (name) return name;
  }
  const colon = detectColonSpeakerBefore(beforeSt);
  if (colon) return colon;
  const tail = detectTailSpeakerAfter(after);
  if (tail) return tail;
  const lineName = detectNameLineBeforeQuote(beforeSt);
  if (lineName) return lineName;
  // Do not use *Sarah calling* here: it cues the phone/UI, not that Sarah speaks the next line.
  return null;
}

function splitSentences(paragraph) {
  return paragraph
    .split(/(?<=[.!?\u2026])\s+(?=[A-Z\u201C\u201D"\u2018\u2019'])/u)
    .map((s) => s.trim())
    .filter(Boolean);
}

function chunkParagraph(paragraph, chapterIndex, seedIdx, castOrder = []) {
  const text = paragraph.trim();
  if (!text) return [];
  const out = [];
  let cursor = 0;
  let idx = seedIdx;
  let unattributedDialogueTurn = 0;
  DIALOGUE_REGEX.lastIndex = 0;
  let m;
  while ((m = DIALOGUE_REGEX.exec(text)) !== null) {
    const pre = text.slice(cursor, m.index).trim();
    if (pre) {
      for (const s of splitSentences(pre)) {
        if (isStandaloneSpeechAttribution(s)) continue;
        out.push({ index: idx++, chapterIndex, text: s, isDialogue: false, speaker: null });
      }
    }
    const quote = (m[1] || m[2] || m[3] || "").trim();
    const before = text.slice(Math.max(0, m.index - CONTEXT_CHARS), m.index);
    const after = text.slice(m.index + m[0].length, m.index + m[0].length + CONTEXT_CHARS);
    let speaker = detectSpeakerFromContext(before, after);
    if (!speaker && castOrder.length) {
      speaker = detectPronounSpeechTagBeforeQuote(before, castOrder);
    }
    if (!speaker && castOrder.length) {
      speaker = detectPronounSpeakerBefore(before, castOrder);
    }
    if (!speaker && castOrder.length) {
      speaker = detectPronounSpeakerAfter(before, after, castOrder);
    }
    if (!speaker && castOrder.length >= 2) {
      speaker = detectNameQuestionOtherSpeaker(quote, castOrder);
    }
    if (!speaker && quote) {
      // Back-and-forth with no "X said" tags still gets two distinct speaker slots for TTS.
      speaker = unattributedDialogueTurn % 2 === 0 ? "Speaker A" : "Speaker B";
      unattributedDialogueTurn += 1;
    }
    if (quote) {
      out.push({ index: idx++, chapterIndex, text: quote, isDialogue: true, speaker });
    }
    cursor = m.index + m[0].length;
  }
  const trailing = text.slice(cursor).trim();
  if (trailing) {
    for (const s of splitSentences(trailing)) {
      if (isStandaloneSpeechAttribution(s)) continue;
      out.push({ index: idx++, chapterIndex, text: s, isDialogue: false, speaker: null });
    }
  }
  return out;
}

/** "Alice said." between quotes — not spoken aloud as narration in most fiction layouts */
function isStandaloneSpeechAttribution(sentence) {
  const s = String(sentence || "").trim();
  if (!s) return false;
  return new RegExp(`^(${NAME_SRC})\\s+(?:${SPEAKER_VERB_SRC})[.!?…]?$`).test(s);
}

function mergeTinyChunks(chunks, maxLen = 280) {
  const out = [];
  for (const chunk of chunks) {
    const last = out[out.length - 1];
    const canMerge =
      last &&
      last.chapterIndex === chunk.chapterIndex &&
      last.isDialogue === chunk.isDialogue &&
      last.speaker === chunk.speaker &&
      last.text.length + chunk.text.length + 1 <= maxLen;
    if (canMerge) {
      last.text = `${last.text} ${chunk.text}`;
    } else {
      out.push({ ...chunk });
    }
  }
  return out.map((c, i) => ({ ...c, index: i }));
}

export function splitIntoChunks(chapters) {
  const chunks = [];
  let idx = 0;
  const fullSource = chapters.map((c) => c.text).join("\n\n");
  const castOrder = extractCastOrdered(fullSource);
  chapters.forEach((chapter, ci) => {
    const paragraphs = chapter.text.split(/\n{2,}/);
    for (const p of paragraphs) {
      const produced = chunkParagraph(p, ci, idx, castOrder);
      idx += produced.length;
      chunks.push(...produced);
    }
  });
  return mergeTinyChunks(chunks);
}

export function detectSpeakers(chunks) {
  const counts = new Map();
  for (const c of chunks) {
    if (c.speaker) counts.set(c.speaker, (counts.get(c.speaker) || 0) + 1);
  }
  return [...counts.entries()]
    .map(([name, count]) => ({ name, count }))
    .sort((a, b) => b.count - a.count);
}
