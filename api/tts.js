"use strict";

const { MsEdgeTTS, OUTPUT_FORMAT } = require("msedge-tts");
const { DEFAULT_VOICE, isValidVoiceId } = require("./_voices");
const {
  textToRichSSML,
  cleanForTTS,
  xmlEscape: builderXmlEscape,
  clampRate: builderClampRate,
  formatRateAsPercent: builderFormatRate,
  autoDetectEmotion,
} = require("./ssml-builder");

const MAX_CHARS = 8000;
const MIN_CHARS = 1;

function safeBody(req) {
  if (!req || req.body == null) return {};
  if (typeof req.body === "object") return req.body;
  try {
    return JSON.parse(req.body);
  } catch (_err) {
    return {};
  }
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
  const clamped = Math.min(0.5, Math.max(-0.5, n));
  return clamped;
}

function formatRateAsPercent(rate) {
  const pct = Math.round(rate * 100);
  if (pct === 0) return "+0%";
  return pct > 0 ? `+${pct}%` : `${pct}%`;
}

async function synthesizeToBuffer(voice, text, rate, pitch, volume, format, richOpts = {}) {
  const tts = new MsEdgeTTS();
  await tts.setMetadata(voice, format);

  const { useRichSSML = true, style = "natural", expressiveness = 0.68, isDialogue = false, role = null, emotionBias = null, voiceDirection = null } = richOpts;

  if (useRichSSML) {
    // Rich emotional SSML path — the key to non-robotic voices
    // Pass raw (unescaped) text; builder handles cleaning + escaping of spoken content only.
    const ssml = textToRichSSML(text, {
      rate,
      pitch,
      volume,
      style,
      expressiveness,
      isDialogue,
      role,
      emotionBias,
      voiceDirection,
      voice,
    });
    const { audioStream } = await tts.rawToStream(ssml);
    return await new Promise((resolve, reject) => {
      const chunks = [];
      let settled = false;
      const done = (err, result) => {
        if (settled) return;
        settled = true;
        try { tts.close(); } catch (_e) { /* ignore */ }
        if (err) reject(err); else resolve(result);
      };
      audioStream.on("data", (chunk) => {
        chunks.push(Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk));
      });
      audioStream.on("end", () => done(null, Buffer.concat(chunks)));
      audioStream.on("close", () => done(null, Buffer.concat(chunks)));
      audioStream.on("error", (err) => done(err));
      setTimeout(() => done(new Error("TTS synthesis timed out after 20s")), 20000).unref?.();
    });
  }

  // Legacy simple prosody path (full backward compat)
  const prosody = {};
  if (rate && rate !== 0) prosody.rate = formatRateAsPercent(rate);
  if (pitch && pitch !== 0) prosody.pitch = `${pitch > 0 ? "+" : ""}${pitch}Hz`;
  if (volume && volume !== 0) prosody.volume = `${volume > 0 ? "+" : ""}${volume}%`;

  const { audioStream } = await tts.toStream(text, prosody);
  return await new Promise((resolve, reject) => {
    const chunks = [];
    let settled = false;
    const done = (err, result) => {
      if (settled) return;
      settled = true;
      try { tts.close(); } catch (_e) { /* ignore */ }
      if (err) reject(err); else resolve(result);
    };
    audioStream.on("data", (chunk) => {
      chunks.push(Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk));
    });
    audioStream.on("end", () => done(null, Buffer.concat(chunks)));
    audioStream.on("close", () => done(null, Buffer.concat(chunks)));
    audioStream.on("error", (err) => done(err));
    setTimeout(() => done(new Error("TTS synthesis timed out after 20s")), 20000).unref?.();
  });
}

module.exports = async function handler(req, res) {
  res.setHeader("Cache-Control", "no-store");
  if (req.method === "OPTIONS") {
    res.setHeader("Access-Control-Allow-Origin", "*");
    res.setHeader("Access-Control-Allow-Headers", "Content-Type");
    res.setHeader("Access-Control-Allow-Methods", "POST, OPTIONS");
    res.status(204).end();
    return;
  }
  if (req.method !== "POST") {
    res.setHeader("Content-Type", "application/json; charset=utf-8");
    res.status(405).json({ status: "error", message: "Use POST /api/tts with JSON body." });
    return;
  }

  const body = safeBody(req);
  const rawText = String(body.text || "").trim();
  if (rawText.length < MIN_CHARS) {
    res.setHeader("Content-Type", "application/json; charset=utf-8");
    res.status(400).json({ status: "error", message: "Provide non-empty text in 'text' field." });
    return;
  }
  if (rawText.length > MAX_CHARS) {
    res.setHeader("Content-Type", "application/json; charset=utf-8");
    res.status(413).json({
      status: "error",
      message: `Chunk too large. Split into parts of ${MAX_CHARS} characters or fewer.`,
      max_chars: MAX_CHARS,
    });
    return;
  }

  const voiceReq = String(body.voice || DEFAULT_VOICE);
  const voice = isValidVoiceId(voiceReq) ? voiceReq : DEFAULT_VOICE;
  const rate = clampRate(body.rate);
  const pitch = Number.isFinite(Number(body.pitch)) ? Math.min(50, Math.max(-50, Number(body.pitch))) : 0;
  const volume = Number.isFinite(Number(body.volume)) ? Math.min(50, Math.max(-50, Number(body.volume))) : 0;
  const requestedFormat = String(body.format || "mp3").toLowerCase();
  const format =
    requestedFormat === "mp3-high"
      ? OUTPUT_FORMAT.AUDIO_24KHZ_96KBITRATE_MONO_MP3
      : OUTPUT_FORMAT.AUDIO_24KHZ_48KBITRATE_MONO_MP3;

  // New rich controls (default ON — this is the audible improvement)
  const style = String(body.style || body.narrationStyle || "natural").toLowerCase();
  const expressiveness = Number.isFinite(Number(body.expressiveness))
    ? Math.max(0, Math.min(1, Number(body.expressiveness)))
    : 0.68;
  const useRichSSML = body.useRichSSML !== false; // default true for human emotion
  const isDialogue = !!body.isDialogue; // per-chunk hint from multi-voice frontend
  const role = body.role ? String(body.role) : null;
  const emotionBias = body.emotionBias ? String(body.emotionBias) : null;
  const voiceDirection = body.voiceDirection ? String(body.voiceDirection) : null;

  // DEBUG: return the rich generated SSML instead of audio (for "Show generated SSML" checkbox + inspection)
  const wantsDebugSSML = !!(body.debugSSML || body.returnSSML || body.debug === "ssml");
  if (wantsDebugSSML) {
    const ssml = useRichSSML
      ? textToRichSSML(rawText, { rate, pitch, volume, style, expressiveness, isDialogue, role, emotionBias, voiceDirection, voice })
      : `<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xmlns:mstts="http://www.w3.org/2001/mstts" xml:lang="en-US"><prosody rate="${formatRateAsPercent(rate)}" pitch="${pitch}Hz" volume="${volume}%">${xmlEscape(rawText)}</prosody></speak>`;
    res.setHeader("Content-Type", "application/json; charset=utf-8");
    res.status(200).json({
      ssml,
      voice,
      style,
      expressiveness,
      isDialogue,
      role,
      emotionBias,
      voiceDirection,
      useRichSSML,
      charCount: rawText.length,
    });
    return;
  }

  // Rich emotional path (preferred for non-robotic voices) vs legacy fallback for stability.
  // We now TRY the full rich SSML (express-as + per-segment prosody/breaks/emphasis from the builder)
  // for actual audio bytes first. Many voices + the Edge endpoint accept it and deliver dramatically
  // more emotional, human delivery. Only on empty result or error do we silently fall back to the
  // proven legacy simple-prosody path. Debug/SSML viewer + Python always see the rich version.
  // This is the key audible improvement for the free Edge path (user's #1 request).
  const richOpts = {
    useRichSSML: true,
    style,
    expressiveness,
    isDialogue,
    role,
    emotionBias,
    voiceDirection,
  };

  let usedRich = false;
  let buffer = null;
  let lastErr = null;

  // Attempt 1: rich emotional SSML for real audible feeling (the whole point of the engine)
  try {
    buffer = await synthesizeToBuffer(voice, rawText, rate, pitch, volume, format, richOpts);
    if (buffer && buffer.length > 0) {
      usedRich = true;
    } else {
      buffer = null;
    }
  } catch (e) {
    lastErr = e;
    buffer = null;
  }

  // Fallback: legacy (guaranteed bytes, slightly flatter prosody)
  if (!buffer || buffer.length === 0) {
    const legacyText = xmlEscape(rawText);
    try {
      buffer = await synthesizeToBuffer(voice, legacyText, rate, pitch, volume, format, {
        useRichSSML: false,
        style,
        expressiveness,
        isDialogue,
        role,
        emotionBias,
        voiceDirection,
      });
      usedRich = false;
    } catch (e2) {
      lastErr = e2;
      buffer = null;
    }
  }

  if (!buffer || buffer.length === 0) {
    const message = lastErr && lastErr.message ? String(lastErr.message) : "Empty audio from both rich and legacy paths";
    res.setHeader("Content-Type", "application/json; charset=utf-8");
    res.status(502).json({ status: "error", message: `TTS synthesis failed: ${message}`, voice, char_count: rawText.length });
    return;
  }

  res.setHeader("Content-Type", "audio/mpeg");
  res.setHeader("Content-Length", String(buffer.length));
  res.setHeader("X-Voice", voice);
  res.setHeader("X-Char-Count", String(rawText.length));
  res.setHeader("X-SSML-Path", usedRich ? "rich-emotional" : "legacy-prosody");
  if (typeof res.status === "function") res.status(200);
  else res.statusCode = 200;
  res.end(buffer);
};

module.exports.xmlEscape = xmlEscape;
module.exports.clampRate = clampRate;
module.exports.formatRateAsPercent = formatRateAsPercent;
module.exports.MAX_CHARS = MAX_CHARS;

module.exports.textToRichSSML = textToRichSSML;
module.exports.cleanForTTS = cleanForTTS;
module.exports.autoDetectEmotion = autoDetectEmotion;
module.exports.builder = require("./ssml-builder");
