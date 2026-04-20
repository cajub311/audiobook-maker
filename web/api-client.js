// Minimal browser client for the audiobook-maker serverless backend.
// Uses POST /api/tts for real Microsoft Edge neural voices and
// GET /api/voices to populate the voice picker.

const DEFAULT_FALLBACK_VOICES = [
  { id: "en-US-AvaMultilingualNeural", label: "Ava (US, Female, Expressive)", locale: "en-US" },
  { id: "en-US-AndrewMultilingualNeural", label: "Andrew (US, Male, Warm)", locale: "en-US" },
  { id: "en-US-GuyNeural", label: "Guy (US, Male, Narrator)", locale: "en-US" },
  { id: "en-US-JennyNeural", label: "Jenny (US, Female, Narrator)", locale: "en-US" },
  { id: "en-GB-RyanNeural", label: "Ryan (GB, Male, Natural)", locale: "en-GB" },
  { id: "en-GB-SoniaNeural", label: "Sonia (GB, Female, Natural)", locale: "en-GB" },
];

export async function fetchVoices() {
  try {
    const res = await fetch("/api/voices", { cache: "default" });
    if (!res.ok) throw new Error(`voices endpoint ${res.status}`);
    const data = await res.json();
    if (!data || !Array.isArray(data.voices) || data.voices.length === 0) {
      throw new Error("voice list empty");
    }
    return { voices: data.voices, default: data.default || data.voices[0].id, source: "api" };
  } catch (err) {
    return {
      voices: DEFAULT_FALLBACK_VOICES,
      default: DEFAULT_FALLBACK_VOICES[0].id,
      source: "fallback",
      error: err && err.message ? err.message : String(err),
    };
  }
}

// Wait ms milliseconds, aborting early if signal fires.
async function sleep(ms, signal) {
  await new Promise((resolve, reject) => {
    const t = setTimeout(resolve, ms);
    signal?.addEventListener("abort", () => {
      clearTimeout(t);
      reject(new DOMException("Aborted", "AbortError"));
    }, { once: true });
  });
}

export async function synthesizeChunk(chunkText, { voice, rate = 0, pitch = 0, format = "mp3", signal } = {}) {
  const body = JSON.stringify({ text: chunkText, voice, rate, pitch, format });
  const MAX_ATTEMPTS = 4; // 1 initial + 3 retries
  let lastErr;

  for (let attempt = 0; attempt < MAX_ATTEMPTS; attempt++) {
    if (signal?.aborted) throw new DOMException("Aborted", "AbortError");

    // Exponential backoff before each retry: 1 s, 2 s, 4 s
    if (attempt > 0) await sleep(1000 * (2 ** (attempt - 1)), signal);

    try {
      const res = await fetch("/api/tts", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body,
        signal,
      });

      // 4xx errors (except 429 rate-limit) are the caller's fault — don't retry.
      if (res.status >= 400 && res.status < 500 && res.status !== 429) {
        let detail = res.statusText;
        try { const d = await res.json(); detail = d.message || JSON.stringify(d); } catch (_) {}
        const err = new Error(`TTS /api/tts ${res.status}: ${detail}`);
        err.status = res.status;
        throw err;
      }

      if (!res.ok) {
        // 429 or 5xx — retryable
        let detail = res.statusText;
        try { const d = await res.json(); detail = d.message || JSON.stringify(d); } catch (_) {}
        lastErr = Object.assign(new Error(`TTS /api/tts ${res.status}: ${detail}`), { status: res.status });
        continue;
      }

      const blob = await res.blob();
      if (!blob || blob.size === 0) throw new Error("TTS returned empty audio");
      return blob;

    } catch (err) {
      if (err.name === "AbortError") throw err;
      // Non-retryable HTTP error — propagate immediately
      if (err.status && err.status >= 400 && err.status < 500 && err.status !== 429) throw err;
      // Network error or retryable — store and loop
      lastErr = err;
    }
  }

  throw lastErr || new Error("TTS synthesis failed after retries");
}

// Legacy stubs kept so the demo can still fall back to the old
// async job simulator if needed. Not used by the new audiobook flow.
export async function startCloudProcess(payload) {
  try {
    const res = await fetch("/api/process", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!res.ok) return { ok: false, status: res.status };
    return { ok: true, data: await res.json() };
  } catch (_err) {
    return { ok: false, status: 0 };
  }
}

export async function pollCloudProcess(jobId) {
  try {
    const res = await fetch(`/api/process?job_id=${encodeURIComponent(jobId)}`);
    if (!res.ok) return { ok: false, status: res.status };
    return { ok: true, data: await res.json() };
  } catch (_err) {
    return { ok: false, status: 0 };
  }
}
