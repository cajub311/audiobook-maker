"use strict";

const { MsEdgeTTS, OUTPUT_FORMAT } = require("msedge-tts");
const { DEFAULT_VOICE, isValidVoiceId } = require("./_voices");

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

async function synthesizeToBuffer(voice, text, rate, pitch, volume, format) {
  const tts = new MsEdgeTTS();
  await tts.setMetadata(voice, format);
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
    setTimeout(() => done(new Error("TTS synthesis timed out after 25s")), 25000).unref?.();
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

  const escapedText = xmlEscape(rawText);

  try {
    const buffer = await synthesizeToBuffer(voice, escapedText, rate, pitch, volume, format);
    if (!buffer || buffer.length === 0) {
      res.setHeader("Content-Type", "application/json; charset=utf-8");
      res.status(502).json({ status: "error", message: "Empty audio response from TTS upstream." });
      return;
    }
    res.setHeader("Content-Type", "audio/mpeg");
    res.setHeader("Content-Length", String(buffer.length));
    res.setHeader("X-Voice", voice);
    res.setHeader("X-Char-Count", String(rawText.length));
    if (typeof res.status === "function") res.status(200);
    else res.statusCode = 200;
    res.end(buffer);
  } catch (err) {
    const message = err && err.message ? String(err.message) : String(err);
    res.setHeader("Content-Type", "application/json; charset=utf-8");
    res.status(502).json({
      status: "error",
      message: `TTS synthesis failed: ${message}`,
      voice,
      char_count: rawText.length,
    });
  }
};

module.exports.xmlEscape = xmlEscape;
module.exports.clampRate = clampRate;
module.exports.formatRateAsPercent = formatRateAsPercent;
module.exports.MAX_CHARS = MAX_CHARS;
