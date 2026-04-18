"use strict";

const { VOICES, DEFAULT_VOICE } = require("./_voices");

module.exports = function handler(_req, res) {
  res.setHeader("Content-Type", "application/json; charset=utf-8");
  res.setHeader("Cache-Control", "public, max-age=3600, s-maxage=86400");
  res.status(200).json({
    status: "ok",
    default: DEFAULT_VOICE,
    count: VOICES.length,
    voices: VOICES,
  });
};
