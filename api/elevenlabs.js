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
 *   - Intended for self-hosted / trusted deployments where the operator wants to offer
 *     a "no key in browser localStorage" premium path.
 *   - The primary / recommended path remains the excellent client-side direct ElevenLabs
 *     calls (key never touches our servers).
 */

const ELEVEN_BASE = "https://api.elevenlabs.io/v1";

function safeBody(req) {
  if (!req || req.body == null) return {};
  if (typeof req.body === "object") return req.body;
  try { return JSON.parse(req.body); } catch (_) { return {}; }
}

module.exports = async function handler(req, res) {
  // CORS (same as /api/tts)
  res.setHeader("Access-Control-Allow-Origin", "*");
  res.setHeader("Access-Control-Allow-Methods", "GET, POST, OPTIONS");
  res.setHeader("Access-Control-Allow-Headers", "Content-Type");

  if (req.method === "OPTIONS") {
    res.status(204).end();
    return;
  }

  const apiKey = process.env.ELEVENLABS_API_KEY && String(process.env.ELEVENLABS_API_KEY).trim();
  const proxyEnabled = !!apiKey;

  if (!proxyEnabled) {
    res.setHeader("Content-Type", "application/json; charset=utf-8");
    res.status(503).json({
      status: "error",
      message: "Server-side ElevenLabs proxy is not enabled on this deployment. " +
               "Set the ELEVENLABS_API_KEY environment variable to activate the secure proxy path. " +
               "The client-side direct ElevenLabs integration (key only in your browser) remains fully available and is the default/recommended option for most users.",
      proxy_enabled: false,
      fallback: "client"
    });
    return;
  }

  // Voices list proxy (GET /api/elevenlabs?voices=1 or ?action=voices)
  const wantsVoices = req.method === "GET" &&
    (req.query && (req.query.voices === "1" || req.query.voices === "true" || req.query.action === "voices"));

  if (wantsVoices) {
    try {
      const r = await fetch(`${ELEVEN_BASE}/voices`, {
        headers: {
          "xi-api-key": apiKey,
          Accept: "application/json",
        },
      });
      if (!r.ok) {
        const txt = await r.text().catch(() => "");
        res.setHeader("Content-Type", "application/json; charset=utf-8");
        res.status(r.status).json({ status: "error", message: `Upstream voices error: ${r.status} ${txt.slice(0, 300)}` });
        return;
      }
      const data = await r.json();
      const voices = (data.voices || []).map((v) => ({
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
    } catch (err) {
      res.setHeader("Content-Type", "application/json; charset=utf-8");
      res.status(502).json({ status: "error", message: "Failed to fetch voices via proxy: " + (err.message || err) });
      return;
    }
  }

  if (req.method !== "POST") {
    res.setHeader("Content-Type", "application/json; charset=utf-8");
    res.status(405).json({ status: "error", message: "Use POST for synthesis or GET ?voices=1" });
    return;
  }

  const body = safeBody(req);
  const text = String(body.text || "").trim();
  if (!text) {
    res.setHeader("Content-Type", "application/json; charset=utf-8");
    res.status(400).json({ status: "error", message: "Provide non-empty 'text'." });
    return;
  }
  if (text.length > 8000) {
    res.setHeader("Content-Type", "application/json; charset=utf-8");
    res.status(413).json({ status: "error", message: "Text too long for proxy chunk (max 8000 chars)." });
    return;
  }

  const voice_id = String(body.voice_id || body.voiceId || "21m00Tcm4TlvDq8ikWAM").trim();
  const model_id = String(body.model_id || body.modelId || "eleven_turbo_v2_5").trim();

  // Accept either full voice_settings object or fall back to sane defaults if missing
  let voice_settings = body.voice_settings || body.voiceSettings;
  if (!voice_settings || typeof voice_settings !== "object") {
    voice_settings = {
      stability: 0.55,
      similarity_boost: 0.82,
      style: 0.55,
      use_speaker_boost: true,
    };
  }

  const output_format = body.output_format || body.outputFormat || "mp3_44100_128";

  const url = `${ELEVEN_BASE}/text-to-speech/${encodeURIComponent(voice_id)}`;

  const elevenBody = {
    text,
    model_id,
    voice_settings,
    output_format,
  };

  try {
    const r = await fetch(url, {
      method: "POST",
      headers: {
        "xi-api-key": apiKey,
        "Content-Type": "application/json",
        Accept: "audio/mpeg",
      },
      body: JSON.stringify(elevenBody),
    });

    if (r.status === 401 || r.status === 403) {
      res.setHeader("Content-Type", "application/json; charset=utf-8");
      res.status(502).json({
        status: "error",
        message: "ElevenLabs auth failed on server proxy (check ELEVENLABS_API_KEY).",
      });
      return;
    }
    if (r.status === 422) {
      let detail = "Invalid voice or settings";
      try {
        const j = await r.json();
        detail = (j.detail && j.detail.message) || JSON.stringify(j.detail) || detail;
      } catch (_) {}
      res.setHeader("Content-Type", "application/json; charset=utf-8");
      res.status(422).json({ status: "error", message: `ElevenLabs 422 via proxy: ${detail}` });
      return;
    }
    if (!r.ok) {
      let detail = r.statusText;
      try { const j = await r.json(); detail = j.detail?.message || j.message || JSON.stringify(j); } catch (_) {}
      res.setHeader("Content-Type", "application/json; charset=utf-8");
      res.status(r.status >= 500 ? 502 : 400).json({
        status: "error",
        message: `ElevenLabs TTS via proxy ${r.status}: ${detail}`,
      });
      return;
    }

    // Stream audio back
    const contentType = r.headers.get("content-type") || "audio/mpeg";
    res.setHeader("Content-Type", contentType);
    const contentLength = r.headers.get("content-length");
    if (contentLength) res.setHeader("Content-Length", contentLength);
    res.setHeader("X-Proxy", "elevenlabs-server");
    res.setHeader("X-Voice-Id", voice_id);

    // Pipe the body
    if (r.body && typeof r.body.pipe === "function") {
      // Node readable stream
      r.body.pipe(res);
    } else {
      const buf = Buffer.from(await r.arrayBuffer());
      res.end(buf);
    }
  } catch (err) {
    const msg = err && err.message ? String(err.message) : String(err);
    res.setHeader("Content-Type", "application/json; charset=utf-8");
    res.status(502).json({
      status: "error",
      message: `Server ElevenLabs proxy failed: ${msg}`,
    });
  }
};
