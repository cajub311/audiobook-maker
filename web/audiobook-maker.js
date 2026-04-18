// Orchestrates the full in-browser audiobook pipeline:
//  1. Split the input text into sensible chunks.
//  2. Send N chunks at a time to /api/tts with the chosen voice.
//  3. Stream each returned MP3 into a single concatenated Blob
//     (MP3 frames can be byte-concatenated safely).
//  4. Report progress through a callback so the UI can update live.

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
}) {
  const chunks = chunkText(text, maxChunkChars);
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
    while (!failure) {
      const index = cursor++;
      if (index >= chunks.length) return;
      try {
        const blob = await synthesizeChunk(chunks[index], { voice, rate, pitch, format, signal });
        parts[index] = blob;
        stats.bytes += blob.size;
        completed += 1;
        if (typeof onChunk === "function") onChunk({ index, blob });
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
  const blob = new Blob(parts, { type: "audio/mpeg" });
  return { blob, chunks, stats };
}
