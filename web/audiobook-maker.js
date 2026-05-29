// Orchestrates the full in-browser audiobook pipeline:
//  1. Split the input text into sensible chunks.
//  2. Send N chunks at a time to /api/tts (free Edge) or direct ElevenLabs (premium, key never leaves browser).
//  3. Stream each returned MP3 into a single concatenated Blob (safe byte concat for MP3).
//  4. Report progress through a callback so the UI can update live.
// Premium support: pass `premium: { apiKey, modelId, voiceId }` — fully client-side.

import { chunkText, describeChunks } from "/web/chunker.js";
import { synthesizeChunk } from "/web/api-client.js";

const DEFAULT_CONCURRENCY = 4;

export async function makeAudiobook({
  text,
  voice,
  rate = 0,
  pitch = 0,
  format = "mp3",
  concurrency = DEFAULT_CONCURRENCY,
  maxChunkChars,
  onProgress,
  onChunk,
  signal,
  // Optional: supply pre-chunked items with per-chunk voice/speaker metadata.
  // Each item is { text: string, voice?: string, rate?, pitch?, isDialogue?, speaker?, role?, emotionBias?, voiceDirection? }.
  // role: per-speaker MS express-as role (YoungAdultFemale etc); emotionBias: style nudge for character voice differentiation.
  // voiceDirection: per-chunk or global AI Director text / [tags] (enables section-specific emotion).
  // When provided, `text` and the default chunker are ignored.
  items,
  // Optional: given a chunk string (or item), return a voice id to use for it.
  voiceResolver,
  // Rich SSML emotion controls (global defaults; items[] can override per chunk)
  style = "natural",
  expressiveness = 0.68,
  useRichSSML = true,
  // Premium ElevenLabs config (client-side only). When present, per-chunk calls go direct to 11labs.
  premium = null, // { apiKey, modelId?, voiceId? }
  // Voice Direction (global from AI Director / Voice Direction field). Per-item can override.
  voiceDirection = null,
}) {
  let chunks;
  let itemsResolved;
  if (Array.isArray(items) && items.length) {
    itemsResolved = items
      .map((it) => (typeof it === "string" ? { text: String(it).trim() } : { ...it, text: String(it.text || "").trim() }))
      .filter((it) => it.text.length > 0);
    chunks = itemsResolved.map((it) => it.text);
  } else {
    chunks = chunkText(text, maxChunkChars);
    itemsResolved = chunks.map((c) => ({ text: c }));
  }
  if (!chunks.length) {
    return { blob: null, chunks: [], stats: { count: 0, totalChars: 0, bytes: 0, durationMs: 0 } };
  }

  const stats = { ...describeChunks(chunks), bytes: 0, durationMs: 0 };
  const start = performance.now();
  const parts = new Array(chunks.length);
  let completed = 0;
  let failure = null;

  const report = () => {
    if (typeof onProgress === "function") {
      onProgress({
        completed,
        total: chunks.length,
        percent: Math.round((completed / chunks.length) * 100),
        bytes: stats.bytes,
      });
    }
  };
  report();

  const limit = Math.max(1, Math.min(8, Number(concurrency) || DEFAULT_CONCURRENCY));

  let cursor = 0;
  const workers = new Array(Math.min(limit, chunks.length)).fill(0).map(async () => {
    while (!failure && !signal?.aborted) {
      const index = cursor++;
      if (index >= chunks.length) return;
      const item = itemsResolved[index];
      let chunkVoice = item.voice || voice;
      if (typeof voiceResolver === "function") {
        const resolved = voiceResolver(item, index);
        if (resolved) chunkVoice = resolved;
      }
      const chunkRate = item.rate != null ? item.rate : rate;
      const chunkPitch = item.pitch != null ? item.pitch : pitch;
      const chunkStyle = item.style != null ? item.style : style;
      const chunkExpr = item.expressiveness != null ? item.expressiveness : expressiveness;
      const chunkRich = item.useRichSSML != null ? item.useRichSSML : useRichSSML;
      const chunkDialogue = !!item.isDialogue;
      const chunkRole = item.role != null ? item.role : null;
      const chunkEmotionBias = item.emotionBias != null ? item.emotionBias : null;
      const chunkVoiceDirection = item.voiceDirection != null ? item.voiceDirection : voiceDirection;
      try {
        const blob = await synthesizeChunk(item.text, {
          voice: chunkVoice,
          rate: chunkRate,
          pitch: chunkPitch,
          format,
          style: chunkStyle,
          expressiveness: chunkExpr,
          useRichSSML: chunkRich,
          isDialogue: chunkDialogue,
          role: chunkRole,
          emotionBias: chunkEmotionBias,
          voiceDirection: chunkVoiceDirection,
          signal,
          premium: premium || (item.premium || null),
        });
        parts[index] = blob;
        stats.bytes += blob.size;
        completed += 1;
        if (typeof onChunk === "function") onChunk({ index, blob, item });
        report();
      } catch (err) {
        failure = err;
        return;
      }
    }
  });

  await Promise.all(workers);
  if (failure) throw failure;

  stats.durationMs = Math.round(performance.now() - start);
  // Filter out any unfilled slots (cancelled or skipped chunks) so the
  // Blob constructor never receives undefined, which would stringify to "undefined".
  const blob = new Blob(parts.filter(Boolean), { type: "audio/mpeg" });
  return { blob, chunks, stats };
}
