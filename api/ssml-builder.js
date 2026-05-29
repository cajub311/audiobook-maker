"use strict";

// SSML builder with rich emotion: autoDetectEmotion, per-segment <mstts:express-as>,
// dialogue roles, prosody, emphasis, and [tag] author overrides (from Voice Direction or inline in text).
// Used by both the free Edge path and exposed for Python parity / tests.

const EMOTION_RULES = [
  {
    name: "sad",
    regex: /\b(sad|sorrow|grief|tears|heartbroken|weep|wept|mourn|mournful|despair|lonely|melancholy|tragically|devastated|funeral|loss|cried|grieving)\b/gi,
    style: "sad",
    degreeFactor: 1.15,
  },
  {
    name: "angry",
    regex: /\b(angry|anger|furious|rage|raged|hate|hatred|shouted|snapped|growled|snarled|damn|bastard|hell|enraged|outraged|furiously|curse)\b/gi,
    style: "angry",
    degreeFactor: 1.22,
  },
  {
    name: "excited",
    regex: /\b(excited|thrilled|amazing|wonderful|joy|ecstatic|fantastic|yay|hurrah|cheered|exhilarated|delighted|joyfully|magnificent)\b/gi,
    style: "cheerful",
    degreeFactor: 1.28,
  },
  {
    name: "whisper",
    regex: /\b(whisper|whispered|softly|quietly|hushed|secret|murmur|muttered|under (his|her|their) breath|confided)\b/gi,
    style: "whisper",
    degreeFactor: 0.78,
  },
  {
    name: "fear",
    regex: /\b(fear|terrified|scared|afraid|trembled|panic|panicked|horror|dread|shudder|afraid|terror)\b/gi,
    style: "terrified",
    degreeFactor: 1.1,
  },
  {
    name: "laugh",
    regex: /\b(laugh|laughed|laughing|chuckle|chuckled|giggled|hilarious|funny|joked|roared with laughter)\b/gi,
    style: "cheerful",
    degreeFactor: 0.9,
  },
  {
    name: "gentle",
    regex: /\b(gently|soft|warmly|tender|caressed|smiled softly|kindly|lovingly)\b/gi,
    style: "empathetic",
    degreeFactor: 0.95,
  },
  {
    name: "ecstatic",
    regex: /\b(ecstatic|ecstasy|bliss|rapture|overjoyed|jubilant|elated)\b/gi,
    style: "cheerful",
    degreeFactor: 1.35,
  },
  {
    name: "betrayal",
    regex: /\b(betray|betrayal|treason|backstab|deceive|heartbreak|devastated)\b/gi,
    style: "sad",
    degreeFactor: 1.25,
  },
];

function detectEmotion(text, globalExpressiveness) {
  if (!text || globalExpressiveness < 0.2) return null;
  let best = null;
  let bestScore = 0;
  for (const rule of EMOTION_RULES) {
    const m = text.match(rule.regex);
    const score = m ? m.length : 0;
    if (score > bestScore) {
      bestScore = score;
      best = rule;
    }
  }
  if (!best) return null;
  const scaled = best.degreeFactor * (0.6 + globalExpressiveness * 0.85);
  const deg = Math.max(0.4, Math.min(1.9, scaled));
  return { style: best.style, degree: deg.toFixed(1), name: best.name };
}

function xmlEscape(text) {
  return String(text).replace(/[<>&"']/g, (char) => {
    switch (char) {
      case "<": return "&lt;";
      case ">": return "&gt;";
      case "&": return "&amp;";
      case '"': return "&quot;";
      case "'": return "&apos;";
      default: return char;
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

function formatPitch(pitch) {
  if (!pitch || pitch === 0) return "+0Hz";
  return `${pitch > 0 ? "+" : ""}${pitch}Hz`;
}

function formatVolume(volume) {
  if (!volume || volume === 0) return "+0%";
  return `${volume > 0 ? "+" : ""}${volume}%`;
}

// Lightweight dialogue segmenter (inspired by web/text.js + nlp/dialogue.py but self-contained for server)
const QUOTE_PATTERNS = [
  // Robust: allow inner apostrophes, common contractions, and most punctuation inside quotes
  /[\u201C\u201D"]([^"\u201C\u201D]{0,600})[\u201C\u201D"]/g,
  /[\u00AB]([^\u00BB]{0,600})[\u00BB]/g,
  /[\u300C]([^\u300D]{0,600})[\u300D]/g,
  /[\u300E]([^\u300F]{0,600})[\u300F]/g,
];

function segmentText(text) {
  const segments = [];
  let lastIndex = 0;
  let matches = [];

  for (const re of QUOTE_PATTERNS) {
    re.lastIndex = 0;
    let m;
    while ((m = re.exec(text)) !== null) {
      matches.push({ start: m.index, end: m.index + m[0].length, dialogue: m[1] || m[2] || "" });
    }
  }
  // Dedup overlapping by position
  matches.sort((a, b) => a.start - b.start || (b.end - b.start) - (a.end - a.start));
  const deduped = [];
  for (const m of matches) {
    if (!deduped.length || m.start >= deduped[deduped.length - 1].end) {
      deduped.push(m);
    }
  }

  for (const m of deduped) {
    if (m.start > lastIndex) {
      const pre = text.slice(lastIndex, m.start).trim();
      if (pre) segments.push({ text: pre, isDialogue: false });
    }
    const d = (m.dialogue || "").trim();
    if (d) segments.push({ text: d, isDialogue: true });
    lastIndex = m.end;
  }
  if (lastIndex < text.length) {
    const trail = text.slice(lastIndex).trim();
    if (trail) segments.push({ text: trail, isDialogue: false });
  }
  return segments.length > 0 ? segments : [{ text, isDialogue: false }];
}

// Simple but effective auto emotion detector (keyword + punctuation heuristics + research-backed cues)
// Returns suggested style and boosted expressiveness for the whole text or a segment.
function autoDetectEmotion(text) {
  const t = String(text || "").toLowerCase();
  let style = "natural";
  let boost = 0;

  const cues = {
    ecstatic: ["amazing", "incredible", "best ever", "fantastic", "ecstatic", "!"],
    excited: ["excited", "can't wait", "wow", "suddenly", "!"],
    sarcastic: ["sure", "yeah right", "of course", "as if"],
    whispering: ["whisper", "quietly", "don't tell", "secret"],
    sad: ["sad", "sorry", "cried", "whispered", "trembling", "lost"],
    angry: ["angry", "furious", "shouted", "how dare", "never"],
    gentle: ["softly", "gently", "warm", "calm", "whispered"],
    intense: ["suddenly", "everything changed", "desperately", "now!"],
  };

  for (const [s, words] of Object.entries(cues)) {
    if (words.some(w => t.includes(w))) {
      style = s;
      boost = 0.15;
      break;
    }
  }

  // Punctuation boosts
  const exclam = (t.match(/!/g) || []).length;
  const q = (t.match(/\?/g) || []).length;
  if (exclam > 1) { style = "excited"; boost += 0.1; }
  if (q > 0 && style === "natural") { style = "conversational"; }

  return { suggestedStyle: style, expressivenessBoost: Math.min(0.3, boost) };
}

// Map high-level style presets + dialogue hint → Microsoft express-as style + degree hint
// Expanded with more from official MS Speech SSML docs (ecstatic, sarcastic, whispering, etc.)
const EXPRESS_MAP = {
  natural: { base: null, dialogue: null },
  dramatic: { base: "narration-professional", dialogue: "cheerful" },
  conversational: { base: "friendly", dialogue: "friendly" },
  gentle: { base: "empathetic", dialogue: "empathetic" },
  intense: { base: "angry", dialogue: "terrified" },
  excited: { base: "cheerful", dialogue: "excited" },
  sad: { base: "sad", dialogue: "empathetic" },
  calm: { base: "calm", dialogue: "gentle" },
};

function pickExpressStyle(style, hasDialogue, expressiveness) {
  const key = String(style || "natural").toLowerCase();
  const map = EXPRESS_MAP[key] || EXPRESS_MAP.natural;
  const chosen = (hasDialogue && map.dialogue) ? map.dialogue : map.base;
  if (!chosen) return null;
  // Only wrap at moderate+ expressiveness to avoid over-stylization on subtle narration.
  if (expressiveness < 0.35) return null;
  return chosen;
}

function getDialogueRole(isDialogue, roleHint) {
  if (roleHint) return roleHint;
  if (!isDialogue) return null;
  // Reasonable defaults for quoted speech differentiation (research-backed for naturalness)
  return "YoungAdultFemale";
}

function buildSegmentSSML(seg, opts = {}) {
  const { ratePct = "+0%", pitchStr = "+0Hz", volStr = "+0%", expressiveness = 0.68, roleHint = null, dialogueHint = false } = opts;
  let content = xmlEscape(seg.text);

  // Gentle word-level emphasis on very short powerful words in emotional contexts
  // Do this FIRST on plain text so later inserted <break time="..."> attributes are not corrupted.
  content = content.replace(/\b(never|always|only|just|really|so|too|completely|utterly|now|no|desperately|run|time)\b/gi, '<emphasis level="moderate">$1</emphasis>');

  // Light emphasis + breathing pauses on natural punctuation (huge for human rhythm)
  content = content.replace(/([,;:])\s+/g, '$1 <break time="180ms"/> ');
  // Sentence terminators inside segment or at segment end (cross-segment attribution cases)
  content = content.replace(/([.!?])\s+(?=[A-Z"'])/g, '$1 <break time="420ms"/> ');
  content = content.replace(/([.!?])(?=\s*$)/g, '$1 <break time="420ms"/> ');
  // Em-dashes and long dashes as natural dramatic pauses
  content = content.replace(/—\s*/g, '— <break time="300ms"/> ');
  content = content.replace(/--\s*/g, '— <break time="280ms"/> ');

  let segContent = `<prosody rate="${ratePct}" pitch="${pitchStr}" volume="${volStr}">${content}</prosody>`;

  // AUTO EMOTION DETECTION per segment (the major upgrade for free voices)
  // Detects sad/angry/excited etc words and wraps the (already prosody-enhanced) content
  // with its own <mstts:express-as> so emotion is localized and powerful.
  const emo = detectEmotion(seg.text, expressiveness);
  if (emo) {
    const role = (seg.isDialogue || dialogueHint) ? getDialogueRole(true, roleHint) : null;
    const roleAttr = role ? ` role="${role}" ` : "";
    segContent = `<mstts:express-as style="${emo.style}" styledegree="${emo.degree}"${roleAttr}>${segContent}</mstts:express-as>`;
  }

  // Consume any remaining [tags] (from Voice Direction or author input) as extra local express-as
  // (research pattern for author control without breaking the auto engine)
  // Strip the tag text after wrapping so it doesn't appear in the spoken output.
  segContent = segContent.replace(/\[(sad|angry|whisper|terrified|cheerful|empathetic|sarcastic|reflective|urgent|gentle)\]/gi, (m, tag) => {
    const style = tag.toLowerCase();
    return `<mstts:express-as style="${style}" styledegree="1.15"></mstts:express-as>`;
  });

  return segContent;
}

function textToRichSSML(text, options = {}) {
  let {
    rate = 0,
    pitch = 0,
    volume = 0,
    style = "natural",
    expressiveness = 0.68,
    isDialogue = false,
    role = null,
    emotionBias = null,
    voiceDirection = null,
  } = options;

  // Auto emotion detection (new improvement blending research + previous agent ideas)
  const auto = autoDetectEmotion(text);
  if (style === "auto" || (expressiveness > 0.5 && auto.expressivenessBoost > 0)) {
    style = auto.suggestedStyle;
    expressiveness = Math.min(0.95, expressiveness + auto.expressivenessBoost);
  }

  // Voice Direction influence (from 🧠 AI Director + Voice Direction field).
  // Supports free text keywords and [tags]. Global nudges here; per-chunk overrides
  // are applied upstream by enriching items[] (prefixing [tags] into chunk text or setting emotionBias).
  // This keeps everything backward-compatible while enabling delightful section-specific emotion.
  if (voiceDirection) {
    const dir = String(voiceDirection).toLowerCase();
    const boosts = {
      whisper: 0.10, whispering: 0.10,
      intense: 0.12,
      dramatic: 0.09,
      angry: 0.13, furious: 0.12,
      sad: 0.09,
      excited: 0.11, ecstatic: 0.13,
      gentle: 0.07,
      terrified: 0.10, fear: 0.09,
      cheerful: 0.10,
      empathetic: 0.08,
      sarcastic: 0.06,
      reflective: 0.05,
      urgent: 0.07,
      calm: 0.03,
    };
    for (const [key, boost] of Object.entries(boosts)) {
      if (dir.includes(key) || dir.includes(`[${key}`)) {
        expressiveness = Math.min(0.96, expressiveness + boost);
        if ((style === "auto" || style === "natural") &&
            ["whisper", "angry", "sad", "cheerful", "empathetic", "terrified", "intense", "dramatic"].includes(key)) {
          style = key === "whisper" ? "whispering" : key;
        }
      }
    }
  }

  // Per-speaker emotion bias (from multi-voice grid controls) — nudges expressiveness + style for character differentiation
  // while preserving all existing autoDetect + global behavior. Fully backward-compatible.
  if (emotionBias) {
    const b = String(emotionBias).toLowerCase().trim();
    const biasBoost = { cheerful: 0.12, excited: 0.15, dramatic: 0.10, intense: 0.14, calm: 0.02, empathetic: 0.06, sad: 0.05, whispering: 0.03, sarcastic: 0.04 };
    if (biasBoost[b] != null) {
      expressiveness = Math.min(0.96, expressiveness + biasBoost[b]);
    }
    const styleCandidates = ["cheerful","empathetic","dramatic","intense","calm","sad","excited","whispering","sarcastic","reflective"];
    if ((style === "auto" || style === "natural") && styleCandidates.includes(b)) {
      style = b;
    }
  }

  const cleaned = cleanForTTS(text);
  if (!cleaned) {
    return `<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xmlns:mstts="http://www.w3.org/2001/mstts" xml:lang="en-US"><prosody rate="+0%" pitch="+0Hz" volume="+0%">...</prosody></speak>`;
  }

  const ratePct = formatRateAsPercent(clampRate(rate));
  const pitchStr = formatPitch(pitch);
  const volStr = formatVolume(volume);

  const segments = segmentText(cleaned);

  const hasDialogue = isDialogue || segments.some((s) => s.isDialogue);

  const expressStyle = pickExpressStyle(style, hasDialogue, expressiveness);

  // Build inner content (buildSegmentSSML now applies per-segment emotion express-as + dialogue prosody)
  const innerParts = segments.map((seg) =>
    buildSegmentSSML(seg, { ratePct, pitchStr, volStr, expressiveness, roleHint: role, dialogueHint: isDialogue })
  );
  let inner = innerParts.join(" ");

  // Top-level express-as wrapper (only if no strong local emotions already applied in segments,
  // or for global narration color on dramatic/calm styles). Avoids over-wrapping.
  const hasLocalEmotion = inner.includes('mstts:express-as');
  if (expressStyle && expressiveness > 0.30 && (!hasLocalEmotion || expressiveness > 0.78)) {
    const roleAttr = role ? ` role="${role}" ` : "";
    inner = `<mstts:express-as style="${expressStyle}" styledegree="${Math.min(1.9, Math.max(0.6, expressiveness * 1.6)).toFixed(1)} "${roleAttr}>${inner}</mstts:express-as>`;
  }

  const lang = "en-US";
  return `<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xmlns:mstts="http://www.w3.org/2001/mstts" xml:lang="${lang}">${inner}</speak>`;
}

function cleanForTTS(text) {
  if (!text) return "";
  let t = String(text);
  // Remove control chars except common whitespace
  t = t.replace(/[\u0000-\u0008\u000B\u000C\u000E-\u001F\u007F]/g, "");
  // Normalize smart quotes/punctuation to plain for maximum voice compatibility
  t = t.replace(/[\u2018\u2019]/g, "'").replace(/[\u201C\u201D]/g, '"');
  t = t.replace(/\u2026/g, "...");
  t = t.replace(/\u2014/g, " — ").replace(/\u2013/g, " – ");
  t = t.replace(/\s+/g, " ").trim();
  return t;
}

// Public surface (used by tts handler, tests, Python parity, and web/text.js mirror)
module.exports = {
  textToRichSSML,
  cleanForTTS,
  autoDetectEmotion,
  detectEmotion,
  buildSegmentSSML,
  segmentText,
  EMOTION_RULES,
  EXPRESS_MAP,
};

module.exports.textToRichSSML = textToRichSSML;
module.exports.cleanForTTS = cleanForTTS;
module.exports.autoDetectEmotion = autoDetectEmotion;
module.exports.detectEmotion = detectEmotion;
module.exports.builderVersion = "director-v1";
