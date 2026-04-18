"use strict";

module.exports = function handler(_req, res) {
  res.setHeader("Content-Type", "application/json; charset=utf-8");
  res.status(200).json({
    project: "audiobook-maker",
    purpose: "Web audiobook maker + launcher instructions for the Python Gradio desktop app.",
    web_demo: "/web/index.html",
    health_endpoint: "/api/health",
    voices_endpoint: "/api/voices",
    tts_endpoint: "/api/tts",
    process_endpoint: "/api/process",
    tts_usage: {
      method: "POST /api/tts",
      body: {
        text: "string (1..8000 chars)",
        voice: "voice id from /api/voices (optional)",
        rate: "number -0.5..0.5 (optional)",
        pitch: "integer Hz -50..50 (optional)",
        volume: "integer % -50..50 (optional)",
        format: "'mp3' (48kbps) or 'mp3-high' (96kbps)",
      },
      response: "audio/mpeg binary stream",
    },
    steps: [
      "Open /web/index.html for the full in-browser audiobook maker.",
      "Or install local desktop app: pip install -r requirements.txt",
      "Run: python3 audiobook_creator_v7.py",
      "Open http://localhost:7860 in your browser",
    ],
    note: "The in-browser web audiobook maker uses /api/tts for real Microsoft Edge neural voices. No API key required.",
  });
};
