"use strict";

// Curated voice catalog endpoint.
// Always re-exports the live VOICES list from ./_voices so any voices another
// agent adds there appear here automatically (never hardcode a copy).
//
// Contract (relied on by tests/clients):
//   200 JSON: { status: "ok", default, count, voices: [{ id, label, locale, ... }] }

const { VOICES, DEFAULT_VOICE } = require("./_voices");

module.exports = function handler(req, res) {
  try {
    res.setHeader("Content-Type", "application/json; charset=utf-8");
    // Catalog is effectively static; cache aggressively at the edge.
    res.setHeader("Cache-Control", "public, max-age=3600, s-maxage=86400");

    const method = req && req.method;
    if (method === "OPTIONS") {
      res.status(204).end();
      return;
    }
    if (method && method !== "GET" && method !== "HEAD") {
      res.status(405).json({ status: "error", message: "Use GET for /api/voices." });
      return;
    }

    const voices = Array.isArray(VOICES) ? VOICES : [];

    res.status(200).json({
      status: "ok",
      default: DEFAULT_VOICE || (voices[0] && voices[0].id) || null,
      count: voices.length,
      voices,
    });
  } catch (err) {
    try {
      res.setHeader("Content-Type", "application/json; charset=utf-8");
      res.status(500).json({ status: "error", message: "Failed to load voice catalog." });
    } catch (_e) {
      /* response already sent */
    }
  }
};
