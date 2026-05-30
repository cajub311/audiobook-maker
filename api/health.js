"use strict";

// Lightweight health/readiness probe.
// Contract (relied on by tests/clients): returns 200 JSON with status: "ok".
// Additive fields (version, capabilities, uptime) are safe to extend.

let pkgVersion = "unknown";
try {
  // Best-effort; never let a missing/unreadable package.json break health.
  pkgVersion = require("../package.json").version || "unknown";
} catch (_err) {
  pkgVersion = "unknown";
}

module.exports = function handler(req, res) {
  try {
    res.setHeader("Content-Type", "application/json; charset=utf-8");
    // Health should never be cached by CDNs/clients.
    res.setHeader("Cache-Control", "no-store, max-age=0");

    const method = req && req.method;
    if (method === "OPTIONS") {
      res.status(204).end();
      return;
    }
    if (method && method !== "GET" && method !== "HEAD") {
      res.status(405).json({ status: "error", message: "Use GET for /api/health." });
      return;
    }

    const elevenProxy = !!(process.env.ELEVENLABS_API_KEY && String(process.env.ELEVENLABS_API_KEY).trim());

    res.status(200).json({
      status: "ok",
      service: "audiobook-maker",
      version: pkgVersion,
      timestamp: new Date().toISOString(),
      uptime_seconds: Math.round(process.uptime ? process.uptime() : 0),
      capabilities: {
        edge_tts: true, // free Microsoft Edge neural voices (default path)
        voices_catalog: true,
        elevenlabs_proxy: elevenProxy, // optional premium server-side proxy
      },
    });
  } catch (err) {
    try {
      res.setHeader("Content-Type", "application/json; charset=utf-8");
      res.status(500).json({ status: "error", message: "Health check failed." });
    } catch (_e) {
      /* response already sent */
    }
  }
};
