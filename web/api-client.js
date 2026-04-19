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

export async function synthesizeChunk(chunkText, { voice, rate = 0, pitch = 0, format = "mp3", signal } = {}) {
  const body = JSON.stringify({ text: chunkText, voice, rate, pitch, format });
  const res = await fetch("/api/tts", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body,
    signal,
  });
  if (!res.ok) {
    let detail = "";
    try {
      const data = await res.json();
      detail = data && data.message ? data.message : JSON.stringify(data);
    } catch (_err) {
      detail = res.statusText;
    }
    const error = new Error(`TTS /api/tts ${res.status}: ${detail}`);
    error.status = res.status;
    throw error;
  }
  const blob = await res.blob();
  if (!blob || blob.size === 0) {
    throw new Error("TTS returned empty audio");
  }
  return blob;
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
