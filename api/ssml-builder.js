"use strict";

// ─── Utilities ────────────────────────────────────────────────────────────────

function xmlEscape(text) {
  return String(text).replace(/[<>&"']/g, (c) => {
    switch (c) {
      case "<": return "&lt;";
      case ">": return "&gt;";
      case "&": return "&amp;";
      case '"': return "&quot;";
      case "'": return "&apos;";
      default: return c;
    }
  });
}

function clampRate(speed) {
  const n = Number(speed);
  if (!Number.isFinite(n)) return 0;
  return Math.min(0.5, Math.max(-0.5, n));
}

function formatRateAsPercent(rate) {
  const pct = Math.round(rate * 100);
  if (pct === 0) return "+0%";
  return pct > 0 ? `+${pct}%` : `${pct}%`;
}

// ─── Text Cleaning ────────────────────────────────────────────────────────────

// Inline emotion override tags like [whisper], [angry], [sad], etc.
const INLINE_TAG_RE = /\[(whisper(?:ing)?|shout(?:ing)?|angry|sad|gentle|excited|laugh(?:ing)?|sob(?:bing)?|dramatic|sarcastic)\]/gi;

function cleanForTTS(text) {
  return String(text).replace(INLINE_TAG_RE, " ").replace(/\s+/g, " ").trim();
}

function extractModifiers(text) {
  const found = [];
  const cleaned = String(text)
    .replace(INLINE_TAG_RE, (_, tag) => { found.push(tag.toLowerCase()); return " "; })
    .replace(/\s+/g, " ")
    .trim();
  return { cleaned, inlineMods: found };
}

// ─── Emotion Detection ────────────────────────────────────────────────────────

// Each rule: [regex, emotion_name, confidence_score]
// Higher score wins when multiple rules match. Ordered roughly high→low confidence.
const EMOTION_RULES = [
  // Explicit voice-acting action verbs — very high confidence
  [/\b(screamed?|shrieked?|shouted?|yelled?|roared?|bellowed?|howled?)\b/i, "angry", 0.92],
  [/\b(sobbed?|wept|wailed?|cried\b|whimpered?)\b/i, "sad", 0.92],
  [/\b(whispered?|murmured?|breathed? softly|said softly|hissed?)\b/i, "whisper", 0.88],
  [/\b(terrified|petrified|trembling|shaking|heart pounding|sheer terror)\b/i, "terrified", 0.92],
  [/\b(laughed?|giggled?|chuckled?|beamed?)\b/i, "excited", 0.78],

  // Strong emotional state vocabulary
  [/\b(furious|outraged?|incensed|seething|raging|livid)\b/i, "angry", 0.82],
  [/\b(devastated|heartbroken|hopeless|despair|grief|sorrowful|desolate|numb)\b/i, "sad", 0.80],
  [/\b(alone|empty|utterly)\b/i, "sad", 0.72],
  [/\b(gentle[yd]?|softly|tenderly|warmly)\b/i, "gentle", 0.68],
  [/\b(ecstatic|overjoyed|thrilled|unbelievable|couldn't believe)\b/i, "excited", 0.75],
  [/\bsuddenly\b/i, "dramatic", 0.65],
  [/\b(catastrophic|devastating|shocking|realized?)\b/i, "dramatic", 0.62],

  // Sarcasm phrasing
  [/\byeah (right|sure|obviously|totally)\b/i, "sarcastic", 0.88],
  [/\boh (sure|right|because|how convenient|perfect)\b/i, "sarcastic", 0.85],
  [/\bas if (that|this)\b/i, "sarcastic", 0.65],

  // Strong anger expressions not covered by vocabulary
  [/\bhow dare\b/i, "angry", 0.80],
  [/\bget out\b.*!/i, "angry", 0.75],

  // Punctuation signals — weakest, tiebreak only
  // Multiple ! in a sentence (not necessarily consecutive) = angry
  [/[^!]*![^!]*!/, "angry", 0.62],
  [/!/, "excited", 0.38],
  [/[—–]/, "dramatic", 0.42],
  [/\.{3}/, "hesitant", 0.36],
];

function autoDetectEmotion(text) {
  let best = { emotion: "neutral", score: 0 };
  for (const [re, emotion, score] of EMOTION_RULES) {
    if (re.test(text) && score > best.score) {
      best = { emotion, score };
    }
  }
  return best;
}

// ─── Style Resolution ─────────────────────────────────────────────────────────

// App-level style names → Microsoft TTS style IDs
const APP_TO_MSTTS = {
  natural:       "narration-professional",
  conversational:"chat",
  dramatic:      "narration-professional",
  intense:       "serious",
  gentle:        "empathetic",
  sarcastic:     "disgruntled",
  whisper:       "whispering",
  whispering:    "whispering",
  sad:           "sad",
  angry:         "angry",
  excited:       "cheerful",
  cheerful:      "cheerful",
  terrified:     "terrified",
  fearful:       "fearful",
  hesitant:      "sad",
  calm:          "calm",
  empathetic:    "empathetic",
  formal:        "newscast-formal",
  storyteller:   "narration-relaxed",
  relaxed:       "narration-relaxed",
  professional:  "narration-professional",
};

// Detected emotion → Microsoft TTS style
const EMOTION_TO_MSTTS = {
  whisper:   "whispering",
  sad:       "sad",
  angry:     "angry",
  excited:   "cheerful",
  gentle:    "empathetic",
  dramatic:  "narration-professional",
  terrified: "terrified",
  fearful:   "fearful",
  sarcastic: "disgruntled",
  hesitant:  "sad",
  neutral:   "narration-professional",
};

// Maximum styledegree at expressiveness=1.0 (SSML spec caps at 2.0)
const MAX_STYLEDEGREE = {
  whispering:              1.0,
  sad:                     1.8,
  angry:                   2.0,
  cheerful:                1.8,
  empathetic:              1.4,
  disgruntled:             1.5,
  terrified:               1.8,
  fearful:                 1.5,
  "narration-professional":1.1,
  "narration-relaxed":     1.0,
  chat:                    1.2,
  serious:                 1.5,
  calm:                    1.0,
  "newscast-formal":       1.0,
};

function resolveStyleAndDegree(appStyle, emotion, expressiveness, isDialogue = false) {
  // Emotion overrides app style when confidence is sufficient
  const emotionStyle = emotion.score >= 0.62 ? EMOTION_TO_MSTTS[emotion.emotion] : null;
  // For dialogue with no strong detected emotion, use chat style for naturalness
  const dialogueFallback = isDialogue && !emotionStyle ? "chat" : null;
  const msttsStyle =
    emotionStyle ||
    dialogueFallback ||
    APP_TO_MSTTS[appStyle] ||
    "narration-professional";

  const maxDeg = MAX_STYLEDEGREE[msttsStyle] || 1.0;
  // Keep a floor of 0.3 so even low expressiveness has some audible effect
  const clampedExpr = Math.max(0.3, Math.min(1.0, expressiveness));
  const degree = Math.max(0.3, Math.min(2.0, maxDeg * clampedExpr));
  return { style: msttsStyle, degree: degree.toFixed(2) };
}

// ─── Dialogue Role Resolution ─────────────────────────────────────────────────

const ROLE_CANONICAL = {
  youngadultfemale: "YoungAdultFemale",
  youngadultmale:   "YoungAdultMale",
  olderadultfemale: "OlderAdultFemale",
  olderadultmale:   "OlderAdultMale",
  girl:             "Girl",
  boy:              "Boy",
  seniorfemale:     "SeniorFemale",
  seniormale:       "SeniorMale",
};

function resolveRole(role) {
  if (!role) return null;
  return ROLE_CANONICAL[String(role).toLowerCase().replace(/\s+/g, "")] || null;
}

// ─── Emotion-Driven Prosody Nudges ────────────────────────────────────────────

// Fine-tune rate and pitch per detected emotion.
// These are blended in at weight = min(1, emotion.score * expressiveness).
const EMOTION_PROSODY_NUDGE = {
  whisper:   { dRate: -0.08, dPitch:  -6 },
  sad:       { dRate: -0.12, dPitch:  -7 },
  angry:     { dRate: +0.08, dPitch: +10 },
  excited:   { dRate: +0.07, dPitch:  +8 },
  gentle:    { dRate: -0.05, dPitch:  -2 },
  dramatic:  { dRate: -0.07, dPitch:  -3 },
  terrified: { dRate: +0.10, dPitch: +14 },
  fearful:   { dRate: +0.05, dPitch:  +5 },
  sarcastic: { dRate: -0.04, dPitch:  -5 },
  hesitant:  { dRate: -0.08, dPitch:  -2 },
};

// ─── SSML Content Assembly ────────────────────────────────────────────────────

// Words that benefit from <emphasis level="strong"> in emotional narration
const EMPHASIS_WORDS = new Set([
  "alone", "empty", "gone", "never", "always", "nothing", "everything", "utterly",
  "completely", "devastated", "heartbroken", "terrified", "shaking", "trembling",
  "finally", "suddenly", "impossible", "unbelievable", "incredible", "catastrophic",
  "devastating", "worst", "best", "only", "last", "first", "ever", "most",
  "silence", "silent", "breathe", "barely", "entire", "single",
]);

// Build the SSML spoken content:
//  - em-dash / en-dash / ellipsis → timed <break> elements
//  - key emotional words → <emphasis level="strong"> (above expressiveness threshold)
function buildSpokenContent(text, expressiveness) {
  // Split at major punctuation breaks; the capturing group keeps separators in the array
  const parts = text.split(/(—|–|\.\.\.)/);
  const segments = [];

  for (const part of parts) {
    if (part === "—") {
      segments.push('<break time="500ms"/>');
    } else if (part === "–") {
      segments.push('<break time="350ms"/>');
    } else if (part === "...") {
      segments.push('<break time="420ms"/>');
    } else if (part) {
      segments.push(applyWordEmphasis(part, expressiveness));
    }
  }

  return segments.join("");
}

// Escape a text segment and optionally wrap high-value words with <emphasis>
function applyWordEmphasis(text, expressiveness) {
  if (expressiveness < 0.55) return xmlEscape(text);

  // split(/\b([A-Za-z]+)\b/) produces alternating [non-word, word, non-word, ...]
  // Odd indices are captured word groups; even indices are separators/punctuation.
  const tokens = text.split(/\b([A-Za-z]+)\b/);
  return tokens.map((token, i) => {
    if (i % 2 === 1 && EMPHASIS_WORDS.has(token.toLowerCase())) {
      return `<emphasis level="strong">${xmlEscape(token)}</emphasis>`;
    }
    return xmlEscape(token);
  }).join("");
}

// ─── Main Builder ─────────────────────────────────────────────────────────────

function textToRichSSML(rawText, opts = {}) {
  const {
    rate         = 0,
    pitch        = 0,
    volume       = 0,
    style        = "natural",
    expressiveness = 0.68,
    isDialogue   = false,
    role         = null,
    emotionBias  = null,
    voiceDirection = null, // reserved for future directorial hints
    voice        = "en-US-AvaMultilingualNeural",
  } = opts;

  // 1. Strip inline modifier tags and clean up whitespace
  const { cleaned, inlineMods } = extractModifiers(rawText);

  // 2. Determine emotion — priority: inline tag > explicit bias > auto-detect
  let emotion;
  if (inlineMods.length > 0) {
    emotion = { emotion: inlineMods[0], score: 1.0 };
  } else if (emotionBias) {
    emotion = { emotion: String(emotionBias).toLowerCase(), score: 0.95 };
  } else {
    emotion = autoDetectEmotion(cleaned);
  }

  // 3. Resolve Microsoft TTS style ID and styledegree
  const { style: msttsStyle, degree: styleDegree } = resolveStyleAndDegree(style, emotion, expressiveness, isDialogue);

  // 4. Resolve dialogue role (affects perceived age/character of voice)
  const msttsRole = resolveRole(role);

  // 5. Compute prosody values — blend base settings with emotion nudges
  const nudge = EMOTION_PROSODY_NUDGE[emotion.emotion] || { dRate: 0, dPitch: 0 };
  const nudgeWeight = Math.min(1.0, emotion.score * expressiveness);
  const finalRate  = clampRate(rate + nudge.dRate * nudgeWeight);
  const finalPitch = Math.max(-50, Math.min(50, pitch + Math.round(nudge.dPitch * nudgeWeight)));

  // 6. Build spoken content with timed breaks and word-level emphasis
  const spokenContent = buildSpokenContent(cleaned, expressiveness);

  // 7. Derive xml:lang from voice locale prefix (e.g. "en-US" from "en-US-AvaMultilingualNeural")
  const lang = voice.match(/^([a-z]{2}-[A-Z]{2})/)?.[1] ?? "en-US";

  // 8. Compose SSML layers from inside out: content → prosody → express-as → voice → speak

  const prosodyParts = [
    finalRate  !== 0 ? `rate="${formatRateAsPercent(finalRate)}"` : "",
    finalPitch !== 0 ? `pitch="${finalPitch >= 0 ? "+" : ""}${finalPitch}Hz"` : "",
    volume     !== 0 ? `volume="${volume >= 0 ? "+" : ""}${volume}%"` : "",
  ].filter(Boolean);

  const withProsody = prosodyParts.length > 0
    ? `<prosody ${prosodyParts.join(" ")}>${spokenContent}</prosody>`
    : spokenContent;

  const expressAttrs = [
    `style="${msttsStyle}"`,
    `styledegree="${styleDegree}"`,
    msttsRole ? `role="${msttsRole}"` : "",
  ].filter(Boolean).join(" ");

  const withExpressAs = `<mstts:express-as ${expressAttrs}>${withProsody}</mstts:express-as>`;

  return (
    `<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis"` +
    ` xmlns:mstts="http://www.w3.org/2001/mstts" xml:lang="${lang}">` +
    `<voice name="${voice}">${withExpressAs}</voice>` +
    `</speak>`
  );
}

// ─── Exports ──────────────────────────────────────────────────────────────────

module.exports = {
  textToRichSSML,
  cleanForTTS,
  xmlEscape,
  clampRate,
  formatRateAsPercent,
  autoDetectEmotion,
};
