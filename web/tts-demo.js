/**
 * Browser SpeechSynthesis helpers: voice pickers, chunking, and queue playback.
 * Chunking avoids long utterances that stall or sound worse on some engines.
 */

const DEFAULT_CHUNK_CHARS = 320;
const PAUSE_MS_BETWEEN_CHUNKS = 80;

/**
 * @param {string} text
 * @param {number} maxChars
 * @returns {string[]}
 */
export function chunkTextForSpeech(text, maxChars = DEFAULT_CHUNK_CHARS) {
  const raw = String(text || "").replace(/\r\n/g, "\n").trim();
  if (!raw) return [];

  const chunks = [];
  let buf = "";
  const flush = () => {
    const t = buf.trim();
    if (t) chunks.push(t);
    buf = "";
  };

  const parts = raw.split(/(\n{2,})/);
  for (const part of parts) {
    if (!part) continue;
    if (/^\n{2,}$/.test(part)) {
      flush();
      continue;
    }
    const sentences = part.split(/(?<=[.!?])\s+/);
    for (const sentence of sentences) {
      const s = sentence.trim();
      if (!s) continue;
      if ((buf + (buf ? " " : "") + s).length <= maxChars) {
        buf = buf ? `${buf} ${s}` : s;
      } else {
        flush();
        if (s.length <= maxChars) {
          buf = s;
        } else {
          for (let i = 0; i < s.length; i += maxChars) {
            const slice = s.slice(i, i + maxChars).trim();
            if (slice) chunks.push(slice);
          }
        }
      }
    }
    flush();
  }
  flush();
  return chunks;
}

/**
 * @param {SpeechSynthesisVoice[]} voices
 * @param {string} langPrefix e.g. "en"
 * @returns {SpeechSynthesisVoice[]}
 */
export function pickEnglishPreferred(voices, langPrefix = "en") {
  const list = voices || [];
  const prefix = langPrefix.toLowerCase();
  const neuralish = list.filter(
    (v) =>
      v.lang &&
      v.lang.toLowerCase().startsWith(prefix) &&
      /neural|premium|natural|enhanced/i.test(`${v.name} ${v.voiceURI}`)
  );
  if (neuralish.length) return neuralish.sort((a, b) => a.name.localeCompare(b.name));
  return list
    .filter((v) => v.lang && v.lang.toLowerCase().startsWith(prefix))
    .sort((a, b) => a.name.localeCompare(b.name));
}

/**
 * @param {SpeechSynthesis} synth
 * @param {string} text
 * @param {object} [opts]
 * @param {string} [opts.voiceURI]
 * @param {number} [opts.rate]
 * @param {number} [opts.pitch]
 * @param {number} [opts.volume]
 * @param {number} [opts.maxChunkChars]
 * @param {number} [opts.pauseMs]
 * @param {(msg: string) => void} [opts.onStatus]
 * @returns {Promise<void>}
 */
export function speakQueuedChunks(synth, text, opts = {}) {
  const {
    voiceURI = "",
    rate = 1.0,
    pitch = 1.0,
    volume = 1.0,
    maxChunkChars = DEFAULT_CHUNK_CHARS,
    pauseMs = PAUSE_MS_BETWEEN_CHUNKS,
    onStatus = () => {},
  } = opts;

  const chunks = chunkTextForSpeech(text, maxChunkChars);
  if (!chunks.length) {
    return Promise.resolve();
  }

  return new Promise((resolve, reject) => {
    let index = 0;

    const runNext = () => {
      if (index >= chunks.length) {
        onStatus("Playback finished.");
        resolve();
        return;
      }
      const piece = chunks[index];
      index += 1;
      onStatus(`Playing part ${index} of ${chunks.length}…`);
      const voices = synth.getVoices();
      const voice =
        (voiceURI && voices.find((v) => v.voiceURI === voiceURI || v.name === voiceURI)) || null;

      const u = new SpeechSynthesisUtterance(piece);
      u.rate = rate;
      u.pitch = pitch;
      u.volume = volume;
      if (voice) u.voice = voice;
      u.onerror = (ev) => {
        reject(ev.error ? new Error(String(ev.error)) : new Error("speech synthesis error"));
      };
      u.onend = () => {
        if (pauseMs > 0 && index < chunks.length) {
          setTimeout(runNext, pauseMs);
        } else {
          runNext();
        }
      };
      synth.speak(u);
    };

    synth.cancel();
    setTimeout(runNext, 0);
  });
}
