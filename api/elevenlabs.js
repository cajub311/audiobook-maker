"use strict";

/**
 * Optional server-side ElevenLabs proxy (OFF by default).
 *
 * POST /api/elevenlabs
 *   Accepts a payload closely matching the ElevenLabs TTS REST body + voice_id:
 *     { text, voice_id, model_id?, voice_settings?, output_format? }
 *   The API key is read ONLY from process.env.ELEVENLABS_API_KEY on the server.
 *   Never logs or returns the key. Returns audio/mpeg on success.
 *
 * GET /api/elevenlabs?voices=1
 *   Proxies the account voices list (useful for "Load my voices" in proxy mode).
 *   Returns { voices: [...] } in the same shape the client expects.
 *
 * Security / UX:
 *   - Completely optional and disabled unless ELEVENLABS_API_KEY is set in the environment.
 *   - When disabled, returns a clear 503 JSON message so the client can fall back gracefully.
 *   - The API key is never logged or echoed back in any response.
 *   - Upstream errors are classified into clear, actionable messages (invalid key vs
 *     quota exhausted vs rate-limited) without leaking provider internals.
 *   - All upstream calls are bounded by an abort timeout so the function can't hang.
 */

const ELEVEN_BASE = "https://api.elevenlabs.io/v1";
const MAX_TEXT_CHARS = 8000;
const VOICES_TIMEOUT_MS = 15000;
const TTS_TIMEOUT_MS = 25000; // under vercel.json maxDuration (30s) to leave headroom

// Free-tier friendly message reused whenever quota is exhausted.
const QUOTA_MESSAGE =
  "ElevenLabs free quota reached — switch off Premium to keep using the unlimited free Edge voices.";

function safeBody(req) {
  if (!req || req.body == null) return {};
  if (typeof req.body === "object") return req.body;
  try {
    const parsed = JSON.parse(req.body);
    return parsed && typeof parsed === "object" ? parsed : {};
  } catch (_err) {
    return {};
  }
}

function sendJson(res, status, payload) {
  res.setHeader("Content-Type", "application/json; charset=utf-8");
  res.setHeader("Cache-Control", "no-store, max-age=0");
  res.status(status).json(payload);
}

// fetch with an abort-based timeout so a stuck upstream can't hang the function.
async function fetchWithTimeout(url, options, timeoutMs) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(url, { ...options, signal: controller.signal });
  } finally {
    clearTimeout(timer);
  }
}

// Detect "quota exhausted" vs "rate limited" — ElevenLabs returns 429 for both,
// but quota errors carry a distinct status/detail. Best-effort, never throws.
function classify429(parsed) {
  const detailStatus =
    parsed && parsed.detail && typeof parsed.detail === "object" ? parsed.detail.status : undefined;
  const blob = JSON.stringify(parsed || {}).toLowerCase();
  const looksLikeQuota =
    (typeof detailStatus === "string" && /quota|credit|limit_exceeded/.test(detailStatus.toLowerCase())) ||
    /quota_exceeded|out of credits|exceeds your.*quota|character.*limit/.test(blob);
  return looksLikeQuota ? "quota" : "rate_limit";
}

// Pull a human-readable detail from an ElevenLabs JSON error without leaking secrets.
function extractDetail(parsed, fallback) {
  if (!parsed) return fallback;
  if (parsed.detail && typeof parsed.detail === "object" && parsed.detail.message) {
    return String(parsed.detail.message);
  }
  if (typeof parsed.detail === "string") return parsed.detail;
  if (parsed.message) return String(parsed.message);
  return fallback;
}

module.exports = async function handler(req, res) {
  // CORS — must mirror vercel.json for /api/elevenlabs (GET, POST, OPTIONS).
  res.setHeader("Access-Control-Allow-Origin", "*");
  res.setHeader("Access-Control-Allow-Methods", "GET, POST, OPTIONS");
  res.setHeader("Access-Control-Allow-Headers", "Content-Type");

  try {
    if (req.method === "OPTIONS") {
      res.status(204).end();
      return;
    }

    const apiKey = process.env.ELEVENLABS_API_KEY && String(process.env.ELEVENLABS_API_KEY).trim();
    const proxyEnabled = !!apiKey;

    if (!proxyEnabled) {
      sendJson(res, 503, {
        status: "error",
        message:
          "Server-side ElevenLabs proxy is not enabled on this deployment. " +
          "Set the ELEVENLABS_API_KEY environment variable to activate the secure proxy path. " +
          "The client-side direct ElevenLabs integration (key only in your browser) remains fully available and is the default/recommended option for most users.",
        proxy_enabled: false,
        fallback: "client",
      });
      return;
    }

    // ---- Voices list proxy (GET /api/elevenlabs?voices=1 or ?action=voices) ----
    const wantsVoices =
      req.method === "GET" &&
      req.query &&
      (req.query.voices === "1" || req.query.voices === "true" || req.query.action === "voices");

    if (wantsVoices) {
      let r;
      try {
        r = await fetchWithTimeout(
          `${ELEVEN_BASE}/voices`,
          { headers: { "xi-api-key": apiKey, Accept: "application/json" } },
          VOICES_TIMEOUT_MS
        );
      } catch (err) {
        const aborted = err && err.name === "AbortError";
        sendJson(res, 504, {
          status: "error",
          message: aborted
            ? "ElevenLabs voices request timed out. Please try again."
            : "Failed to reach ElevenLabs to load voices. Please try again.",
        });
        return;
      }

      if (r.status === 401 || r.status === 403) {
        sendJson(res, 502, {
          status: "error",
          message: "ElevenLabs rejected the server API key (invalid or revoked). Contact the site operator.",
          reason: "invalid_key",
        });
        return;
      }
      if (r.status === 429) {
        let parsed = null;
        try { parsed = await r.json(); } catch (_e) {}
        const kind = classify429(parsed);
        sendJson(res, kind === "quota" ? 402 : 429, {
          status: "error",
          message: kind === "quota" ? QUOTA_MESSAGE : "ElevenLabs is rate-limiting requests. Please retry shortly.",
          reason: kind === "quota" ? "quota_exhausted" : "rate_limited",
        });
        return;
      }
      if (!r.ok) {
        let parsed = null;
        try { parsed = await r.json(); } catch (_e) {}
        const detail = extractDetail(parsed, `upstream ${r.status}`);
        sendJson(res, r.status >= 500 ? 502 : 400, {
          status: "error",
          message: `Could not load ElevenLabs voices: ${String(detail).slice(0, 300)}`,
        });
        return;
      }

      let data;
      try {
        data = await r.json();
      } catch (_e) {
        sendJson(res, 502, { status: "error", message: "ElevenLabs returned an unreadable voices response." });
        return;
      }
      const voices = (Array.isArray(data.voices) ? data.voices : []).map((v) => ({
        id: v.voice_id,
        name: v.name,
        category: v.category || "custom",
        labels: v.labels || {},
        preview_url: v.preview_url || null,
      }));
      res.setHeader("Content-Type", "application/json; charset=utf-8");
      res.setHeader("Cache-Control", "private, max-age=60"); // short cache; account-specific
      res.status(200).json({ voices, source: "server-proxy" });
      return;
    }

    if (req.method !== "POST") {
      sendJson(res, 405, { status: "error", message: "Use POST for synthesis or GET ?voices=1" });
      return;
    }

    // ---- TTS synthesis ----
    const body = safeBody(req);
    const text = String(body.text == null ? "" : body.text).trim();
    if (!text) {
      sendJson(res, 400, { status: "error", message: "Provide non-empty 'text'." });
      return;
    }
    if (text.length > MAX_TEXT_CHARS) {
      sendJson(res, 413, {
        status: "error",
        message: `Text too long for proxy chunk (max ${MAX_TEXT_CHARS} chars).`,
      });
      return;
    }

    const voice_id = String(body.voice_id || body.voiceId || "21m00Tcm4TlvDq8ikWAM").trim();
    const model_id = String(body.model_id || body.modelId || "eleven_turbo_v2_5").trim();

    // Accept a full voice_settings object or fall back to sane defaults if missing/invalid.
    let voice_settings = body.voice_settings || body.voiceSettings;
    if (!voice_settings || typeof voice_settings !== "object" || Array.isArray(voice_settings)) {
      voice_settings = {
        stability: 0.55,
        similarity_boost: 0.82,
        style: 0.55,
        use_speaker_boost: true,
      };
    }

    const output_format =
      typeof body.output_format === "string"
        ? body.output_format
        : typeof body.outputFormat === "string"
        ? body.outputFormat
        : "mp3_44100_128";

    const url = `${ELEVEN_BASE}/text-to-speech/${encodeURIComponent(voice_id)}`;
    const elevenBody = { text, model_id, voice_settings, output_format };

    let r;
    try {
      r = await fetchWithTimeout(
        url,
        {
          method: "POST",
          headers: {
            "xi-api-key": apiKey,
            "Content-Type": "application/json",
            Accept: "audio/mpeg",
          },
          body: JSON.stringify(elevenBody),
        },
        TTS_TIMEOUT_MS
      );
    } catch (err) {
      const aborted = err && err.name === "AbortError";
      sendJson(res, 504, {
        status: "error",
        message: aborted
          ? "ElevenLabs synthesis timed out. Try a shorter chunk or retry."
          : "Failed to reach ElevenLabs for synthesis. Please retry.",
      });
      return;
    }

    if (r.status === 401 || r.status === 403) {
      sendJson(res, 502, {
        status: "error",
        message: "ElevenLabs auth failed on server proxy (the server API key is invalid or revoked).",
        reason: "invalid_key",
      });
      return;
    }

    if (r.status === 429) {
      let parsed = null;
      try { parsed = await r.json(); } catch (_e) {}
      const kind = classify429(parsed);
      sendJson(res, kind === "quota" ? 402 : 429, {
        status: "error",
        message: kind === "quota" ? QUOTA_MESSAGE : "ElevenLabs is rate-limiting requests. Please retry in a few seconds.",
        reason: kind === "quota" ? "quota_exhausted" : "rate_limited",
      });
      return;
    }

    if (r.status === 422) {
      let parsed = null;
      try { parsed = await r.json(); } catch (_e) {}
      const detail = extractDetail(parsed, "Invalid voice or settings");
      sendJson(res, 422, { status: "error", message: `ElevenLabs 422 via proxy: ${String(detail).slice(0, 300)}` });
      return;
    }

    if (!r.ok) {
      let parsed = null;
      try { parsed = await r.json(); } catch (_e) {}
      const detail = extractDetail(parsed, r.statusText || `status ${r.status}`);
      sendJson(res, r.status >= 500 ? 502 : 400, {
        status: "error",
        message: `ElevenLabs TTS via proxy ${r.status}: ${String(detail).slice(0, 300)}`,
      });
      return;
    }

    // ---- Success: stream/return audio ----
    const contentType = r.headers.get("content-type") || "audio/mpeg";
    res.setHeader("Content-Type", contentType);
    res.setHeader("Cache-Control", "no-store, max-age=0");
    const contentLength = r.headers.get("content-length");
    if (contentLength) res.setHeader("Content-Length", contentLength);
    res.setHeader("X-Proxy", "elevenlabs-server");
    res.setHeader("X-Voice-Id", voice_id);

    if (r.body && typeof r.body.pipe === "function") {
      // Node readable stream — pipe through, handle stream errors gracefully.
      r.body.on("error", () => {
        try {
          if (!res.headersSent) {
            sendJson(res, 502, { status: "error", message: "ElevenLabs audio stream failed mid-transfer." });
          } else {
            res.end();
          }
        } catch (_e) {
          /* ignore */
        }
      });
      r.body.pipe(res);
    } else {
      const buf = Buffer.from(await r.arrayBuffer());
      res.end(buf);
    }
  } catch (err) {
    // Never leak the key or raw internals; keep a generic, safe message.
    const msg = err && err.message ? String(err.message) : "unknown error";
    try {
      if (!res.headersSent) {
        sendJson(res, 502, {
          status: "error",
          message: `Server ElevenLabs proxy failed: ${msg.slice(0, 200)}`,
        });
      } else {
        res.end();
      }
    } catch (_e) {
      /* response already sent */
    }
  }
};
