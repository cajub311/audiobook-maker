/* generate rich vs basic SSML + mock premium settings for the emotional corpus */
"use strict";

const fs = require("fs");
const path = require("path");
const { textToRichSSML } = require("../../api/ssml-builder");

const CORPUS = require("./corpus");
const OUT_DIR = path.join(__dirname, "outputs");

function basicSSML(text) {
  const escaped = String(text).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  return `<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="en-US"><prosody rate="+0%" pitch="+0Hz" volume="+0%">${escaped}</prosody></speak>`;
}

function mockElevenSettings(style, expressiveness) {
  const base = { stability: 0.55, similarity_boost: 0.82, style: 0.55, use_speaker_boost: true };
  const exp = Math.max(0.2, Math.min(0.95, Number(expressiveness) || 0.68));
  if (style === "sad") return { ...base, stability: Math.max(0.35, 0.65 - exp * 0.3), style: 0.25 + exp * 0.3 };
  if (style === "angry" || style === "intense") return { ...base, stability: Math.max(0.25, 0.6 - exp * 0.4), style: 0.4 + exp * 0.5 };
  if (style === "excited" || style === "cheerful") return { ...base, stability: 0.4 + (1 - exp) * 0.3, style: 0.3 + exp * 0.6 };
  if (style === "whisper") return { ...base, stability: 0.75, style: 0.15, similarity_boost: 0.88 };
  return { ...base, style: 0.35 + exp * 0.4 };
}

function run({ write = false } = {}) {
  if (write && !fs.existsSync(OUT_DIR)) fs.mkdirSync(OUT_DIR, { recursive: true });

  const reports = [];

  for (const sample of CORPUS) {
    const rich = textToRichSSML(sample.text, {
      style: sample.defaultStyle,
      expressiveness: sample.defaultExpress,
    });
    const basic = basicSSML(sample.text);
    const mockPremium = mockElevenSettings(sample.defaultStyle, sample.defaultExpress);

    const report = {
      id: sample.id,
      category: sample.category,
      text: sample.text,
      listeningNotes: sample.listeningNotes,
      defaultStyle: sample.defaultStyle,
      defaultExpress: sample.defaultExpress,
      richSSML: rich,
      basicSSML: basic,
      mockEleven: mockPremium,
    };
    reports.push(report);

    if (write) {
      fs.writeFileSync(path.join(OUT_DIR, `${sample.id}-rich.ssml`), rich);
      fs.writeFileSync(path.join(OUT_DIR, `${sample.id}-basic.ssml`), basic);
      fs.writeFileSync(path.join(OUT_DIR, `${sample.id}-report.txt`), JSON.stringify(report, null, 2));
    }
  }

  const fullReport = {
    generatedAt: new Date().toISOString(),
    count: reports.length,
    samples: reports,
  };

  if (write) {
    fs.writeFileSync(path.join(OUT_DIR, "FULL-REPORT.txt"), JSON.stringify(fullReport, null, 2));
    console.log(`Wrote ${reports.length} samples + FULL-REPORT.txt to ${OUT_DIR}`);
  } else {
    console.log(JSON.stringify(fullReport, null, 2));
  }
  return fullReport;
}

if (require.main === module) {
  const write = process.argv.includes("--write");
  run({ write });
}

module.exports = { run };