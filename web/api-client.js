// Minimal browser client for the audiobook-maker serverless backend.
// Uses POST /api/tts for real Microsoft Edge neural voices and
// GET /api/voices to populate the voice picker.
//
// Premium paths for ElevenLabs:
//   - Default (excellent): direct client fetch (key only in localStorage, never sent to our servers).
//   - Optional secure server proxy: when premium.serverProxy === true (no apiKey sent).
//     Calls POST /api/elevenlabs which keeps the key on the server via ELEVENLABS_API_KEY env var.
//     Falls back gracefully when proxy is disabled (503) — client can then prompt for key.

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

export async function synthesizeChunk(chunkText, { voice, rate = 0, pitch = 0, format = "mp3", style, expressiveness, useRichSSML, isDialogue, role, emotionBias, voiceDirection, signal, premium } = {}) {
  // Optional secure server-side ElevenLabs proxy (key never leaves server)
  if (premium && premium.serverProxy) {
    return synthesizeWithElevenLabsProxy(chunkText, {
      modelId: premium.modelId,
      voiceId: premium.voiceId,
      style,
      expressiveness,
      signal,
      format,
    });
  }

  // Premium ElevenLabs path (client-only, key in localStorage only — never touches our backend)
  if (premium && premium.apiKey) {
    return synthesizeWithElevenLabs(chunkText, {
      apiKey: premium.apiKey,
      modelId: premium.modelId,
      voiceId: premium.voiceId,
      style,
      expressiveness,
      signal,
      format,
    });
  }

  const payload = { text: chunkText, voice, rate, pitch, format };
  if (style) payload.style = style;
  if (typeof expressiveness === "number") payload.expressiveness = expressiveness;
  if (typeof useRichSSML === "boolean") payload.useRichSSML;
  if (typeof isDialogue === "boolean") payload.isDialogue = isDialogue;
  if (role) payload.role = role;
  if (emotionBias) payload.emotionBias = emotionBias;
  if (voiceDirection) payload.voiceDirection = voiceDirection;
  const body = JSON.stringify(payload);
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

// ===== Premium ElevenLabs mapping (shared by direct + proxy) =====
// Improved to better use high expressiveness (often driven by "Auto (detect...)" + slider
// for emotional samples): significantly lower stability + raise style exaggeration.
function mapStyleToElevenSettings(style = "natural", expressiveness = 0.5) {
  const e = Math.max(0, Math.min(1, Number(expressiveness) || 0.5));
  let stability = 0.78 - (e * 0.58);
  stability = Math.max(0.18, Math.min(0.92, stability));

  let styleExag = e * 0.72;
  const s = String(style || "natural").toLowerCase();

  if (["dramatic", "intense", "excited"].includes(s)) {
    styleExag = Math.min(1.0, styleExag + 0.22);
    stability = Math.max(0.12, stability - 0.08);
  } else if (["gentle", "calm", "conversational"].includes(s)) {
    styleExag = Math.max(0.03, styleExag - 0.18);
    stability = Math.min(0.88, stability + 0.08);
  }

  // High-express samples (typical when Auto emotion detection + high slider):
  // deliberately more dynamic / "performed" delivery from ElevenLabs.
  if (e >= 0.82) {
    stability = Math.max(0.05, stability - 0.18);
    styleExag = Math.min(1.0, styleExag + 0.20);
  } else if (e >= 0.68) {
    stability = Math.max(0.08, stability - 0.10);
    styleExag = Math.min(1.0, styleExag + 0.12);
  } else if (e >= 0.50) {
    stability = Math.max(0.12, stability - 0.04);
    styleExag = Math.min(1.0, styleExag + 0.05);
  }

  // "auto" style means the global expressiveness already encodes detected emotional intensity.
  if (s === "auto") {
    if (e > 0.75) {
      stability = Math.max(0.05, stability - 0.05);
    }
  }

  return {
    stability: Number(stability.toFixed(2)),
    similarity_boost: 0.82,
    style: Number(Math.min(1, Math.max(0, styleExag)).toFixed(2)),
    use_speaker_boost: true,
  };
}

async function sleepForEleven(ms, signal) {
  await new Promise((resolve, reject) => {
    const t = setTimeout(resolve, ms);
    signal?.addEventListener("abort", () => {
      clearTimeout(t);
      reject(new DOMException("Aborted", "AbortError"));
    }, { once: true });
  });
}

// Direct browser-to-ElevenLabs (original excellent path — key stays in browser only)
export async function synthesizeWithElevenLabs(
  text,
  { apiKey, modelId = "eleven_turbo_v2_5", voiceId = "21m00Tcm4TlvDq8ikWAM", style, expressiveness, signal, format } = {}
) {
  if (!apiKey) throw new Error("ElevenLabs API key required for premium path");
  const trimmed = String(text || "").trim();
  if (!trimmed) throw new Error("Empty text for ElevenLabs synthesis");

  const voice_id = String(voiceId || "21m00Tcm4TlvDq8ikWAM").trim();
  const model_id = String(modelId || "eleven_turbo_v2_5").trim();

  const voiceSettings = mapStyleToElevenSettings(style, expressiveness);

  const url = `https://api.elevenlabs.io/v1/text-to-speech/${encodeURIComponent(voice_id)}`;

  const body = {
    text: trimmed,
    model_id,
    voice_settings: voiceSettings,
    output_format: "mp3_44100_128",
  };

  const MAX_ATTEMPTS = 3;
  let lastErr;

  for (let attempt = 0; attempt < MAX_ATTEMPTS; attempt++) {
    if (signal?.aborted) throw new DOMException("Aborted", "AbortError");

    if (attempt > 0) await sleepForEleven(1200 * (2 ** (attempt - 1)), signal);

    try {
      const res = await fetch(url, {
        method: "POST",
        headers: {
          "xi-api-key": apiKey,
          "Content-Type": "application/json",
          Accept: "audio/mpeg",
        },
        body: JSON.stringify(body),
        signal,
      });

      if (res.status === 401 || res.status === 403) {
        const err = new Error("ElevenLabs auth failed — check your API key (must start with your key, never shared).");
        err.status = res.status;
        throw err;
      }
      if (res.status === 422) {
        let detail = "Invalid voice ID or parameters";
        try { const j = await res.json(); detail = j.detail?.message || JSON.stringify(j.detail) || detail; } catch (_) {}
        const err = new Error(`ElevenLabs voice/model error (422): ${detail}. Use a valid voice_id from your dashboard or presets.`);
        err.status = 422;
        throw err;
      }
      if (res.status >= 400 && res.status < 500 && res.status !== 429) {
        let detail = res.statusText;
        try { const j = await res.json(); detail = j.detail?.message || j.message || JSON.stringify(j); } catch (_) {}
        const err = new Error(`ElevenLabs TTS ${res.status}: ${detail}`);
        err.status = res.status;
        throw err;
      }

      if (!res.ok) {
        let detail = res.statusText;
        try { const j = await res.json(); detail = j.detail?.message || j.message || JSON.stringify(j); } catch (_) {}
        lastErr = Object.assign(new Error(`ElevenLabs TTS ${res.status}: ${detail}`), { status: res.status });
        continue; // retry on 429 / 5xx
      }

      const blob = await res.blob();
      if (!blob || blob.size === 0) throw new Error("ElevenLabs returned empty audio");
      return blob;

    } catch (err) {
      if (err.name === "AbortError") throw err;
      if (err.status && err.status >= 400 && err.status < 500 && err.status !== 429) throw err;
      lastErr = err;
    }
  }

  throw lastErr || new Error("ElevenLabs synthesis failed after retries (check key, voice ID, quota)");
}

// ===== NEW: Optional server proxy path for ElevenLabs =====
// Uses POST /api/elevenlabs (key lives only in server env var).
// Accepts same logical inputs; mapping is performed here so behavior matches direct path.
export async function synthesizeWithElevenLabsProxy(
  text,
  { modelId = "eleven_turbo_v2_5", voiceId = "21m00Tcm4TlvDq8ikWAM", style, expressiveness, signal } = {}
) {
  const trimmed = String(text || "").trim();
  if (!trimmed) throw new Error("Empty text for ElevenLabs synthesis");

  const voice_id = String(voiceId || "21m00Tcm4TlvDq8ikWAM").trim();
  const model_id = String(modelId || "eleven_turbo_v2_5").trim();

  const voiceSettings = mapStyleToElevenSettings(style, expressiveness);

  const body = {
    text: trimmed,
    voice_id,
    model_id,
    voice_settings: voiceSettings,
    output_format: "mp3_44100_128",
  };

  const MAX_ATTEMPTS = 3;
  let lastErr;

  for (let attempt = 0; attempt < MAX_ATTEMPTS; attempt++) {
    if (signal?.aborted) throw new DOMException("Aborted", "AbortError");

    if (attempt > 0) await sleepForEleven(1100 * (2 ** (attempt - 1)), signal);

    try {
      const res = await fetch("/api/elevenlabs", {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "audio/mpeg" },
        body: JSON.stringify(body),
        signal,
      });

      if (res.status === 503) {
        // Proxy explicitly disabled on server — surface actionable message
        let msg = "Server proxy disabled";
        try { const j = await res.json(); msg = j.message || msg; } catch (_) {}
        const err = new Error(msg + " — enter your ElevenLabs key above for the direct browser path (recommended).");
        err.status = 503;
        err.fallbackToClientKey = true;
        throw err;
      }

      if (res.status >= 400 && res.status < 500 && res.status !== 429) {
        let detail = res.statusText;
        try { const j = await res.json(); detail = j.message || JSON.stringify(j); } catch (_) {}
        const err = new Error(`ElevenLabs proxy ${res.status}: ${detail}`);
        err.status = res.status;
        throw err;
      }

      if (!res.ok) {
        let detail = res.statusText;
        try { const j = await res.json(); detail = j.message || JSON.stringify(j); } catch (_) {}
        lastErr = Object.assign(new Error(`ElevenLabs proxy ${res.status}: ${detail}`), { status: res.status });
        continue;
      }

      const blob = await res.blob();
      if (!blob || blob.size === 0) throw new Error("ElevenLabs proxy returned empty audio");
      return blob;

    } catch (err) {
      if (err.name === "AbortError") throw err;
      if (err.status && err.status >= 400 && err.status < 500 && err.status !== 429) throw err;
      lastErr = err;
    }
  }

  throw lastErr || new Error("ElevenLabs server proxy failed after retries");
}

// Helper to fetch user's ElevenLabs voices (client-side direct only)
export async function fetchElevenVoices(apiKey) {
  if (!apiKey) throw new Error("API key required");
  const res = await fetch("https://api.elevenlabs.io/v1/voices", {
    headers: { "xi-api-key": apiKey, Accept: "application/json" },
  });
  if (!res.ok) {
    const txt = await res.text().catch(() => "");
    throw new Error(`Failed to load voices (${res.status}): ${txt.slice(0, 200)}`);
  }
  const data = await res.json();
  const voices = (data.voices || []).map((v) => ({
    id: v.voice_id,
    name: v.name,
    category: v.category || "custom",
    labels: v.labels || {},
    preview_url: v.preview_url || null,
  }));
  return voices;
}

// NEW: Fetch voices via the optional server proxy (uses server's ELEVENLABS_API_KEY account)
export async function fetchElevenVoicesViaProxy() {
  const res = await fetch("/api/elevenlabs?voices=1", { cache: "no-store" });
  if (!res.ok) {
    let msg = `Proxy voices failed (${res.status})`;
    try { const j = await res.json(); msg = j.message || msg; } catch (_) {}
    throw new Error(msg);
  }
  const data = await res.json();
  return data.voices || [];
}
