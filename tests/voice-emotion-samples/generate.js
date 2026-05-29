#!/usr/bin/env node
"use strict";

/**
 * Voice Emotion Samples Generator + A/B Reporter
 *
 * Usage:
 *   node tests/voice-emotion-samples/generate.js
 *   node tests/voice-emotion-samples/generate.js --write
 *   node tests/voice-emotion-samples/generate.js --help
 *
 * - Loads the emotional test corpus (13 carefully chosen short passages)
 * - Uses the *local* rich SSML builder (api/ssml-builder.js) for the "free" path
 * - Generates "mock premium" using basic SSML (legacy path) + simulated ElevenLabs voice settings
 * - Prints a clean console A/B report highlighting SSML differences + practical listening notes
 * - With --write: also emits individual .ssml files + a full report.txt for easy iteration
 *
 * Goal: Rapidly iterate on emotional delivery, prosody, express-as styles, breaks,
 * emphasis, dialogue role handling, and punctuation intelligence without needing
 * the full web UI or real audio synthesis every time.
 *
 * Run this often while tuning EMOTION_RULES, autoDetectEmotion, buildSegmentSSML, etc.
 */

const fs = require("fs");
const path = require("path");

// Local rich SSML builder (the real one used by the free Edge path)
// From tests/voice-emotion-samples/ we go up two levels to project root, then into api/
const builder = require("../../api/ssml-builder");
const { textToRichSSML, textToBasicSSML, autoDetectEmotion } = builder;

// Corpus of emotional test cases
const corpus = require("./corpus");

// Simple inline version of the ElevenLabs mapping (from web/api-client.js)
// Used only for the "mock premium" simulation report — not for actual synthesis.
function mockElevenLabsSettings(style = "natural", expressiveness = 0.5) {
  const e = Math.max(0, Math.min(1, Number(expressiveness) || 0.5));
  let stability = 0.78 - (e * 0.58);
  stability = Math.max(0.18, Math.min(0.92, stability));

  let styleExag = e * 0.72;
  const s = String(style || "natural").toLowerCase();
  if (["dramatic", "intense", "excited"].includes(s)) {
    styleExag = Math.min(1.0, styleExag + 0.22);
    stability = Math.max(0.12, stability - 0.08);
  } else if (["gentle", "calm", "conversational", "sad"].includes(s)) {
    styleExag = Math.max(0.03, styleExag - 0.18);
    stability = Math.min(0.88, stability + 0.08);
  }

  return {
    stability: Number(stability.toFixed(2)),
    similarity_boost: 0.82,
    style: Number(Math.min(1, Math.max(0, styleExag)).toFixed(2)),
    use_speaker_boost: true,
  };
}

function formatDiffHighlights(rich, basic) {
  const hasExpress = rich.includes("mstts:express-as");
  const expressCount = (rich.match(/mstts:express-as/g) || []).length;
  const breakCount = (rich.match(/<break /g) || []).length;
  const emphasisCount = (rich.match(/<emphasis /g) || []).length;
  const prosodyLocal = (rich.match(/<prosody /g) || []).length - 1; // minus the outer one

  const lines = [];
  lines.push(`  • Rich adds mstts:express-as wrappers: ${hasExpress ? "YES" : "NO"} (${expressCount} total)`);
  lines.push(`  • Strategic <break> elements inserted: ${breakCount}`);
  lines.push(`  • <emphasis> tags on emotional words: ${emphasisCount}`);
  lines.push(`  • Local <prosody> tweaks (questions/exclamations/dialogue): ${Math.max(0, prosodyLocal)}`);
  lines.push(`  • Basic path is pure cleaned text inside a single outer <prosody> — zero emotion intelligence.`);

  if (rich.includes('style="sad"') || rich.includes('style="angry"')) {
    lines.push(`  • Detected strong emotion styles (sad/angry/etc) — key for timbre change.`);
  }
  if (rich.includes('role="YoungAdultFemale"')) {
    lines.push(`  • Dialogue role attribute present — spoken lines should feel like a distinct character.`);
  }
  if (rich.includes("+7Hz") || rich.includes("+6Hz")) {
    lines.push(`  • Question/exclamation pitch lifts active.`);
  }
  return lines.join("\n");
}

function printSection(title) {
  const bar = "─".repeat(78);
  console.log("\n" + bar);
  console.log(title);
  console.log(bar);
}

function truncateForConsole(str, max = 920) {
  if (str.length <= max) return str;
  return str.slice(0, max) + "\n... [truncated for console — full version written to disk if --write used]";
}

function run() {
  const args = process.argv.slice(2);
  const doWrite = args.includes("--write") || args.includes("-w");
  const showHelp = args.includes("--help") || args.includes("-h");

  if (showHelp) {
    console.log(`
Voice Emotion Samples — A/B Generator for SSML Tuning

Usage:
  node tests/voice-emotion-samples/generate.js
  node tests/voice-emotion-samples/generate.js --write     (also writes .ssml + report.txt)

This script exercises the exact same rich SSML builder that powers the free
Microsoft Edge neural path in production. Use the generated SSML + listening
notes to rapidly judge and improve emotional performance (sad, angry, excited,
sarcastic, whispering, dramatic, questions, dialogue role, breaks, emphasis).

You can feed any of the generated *-free.ssml files directly into the Edge TTS
raw SSML endpoint or the web UI debug mode for audible validation.
`);
    process.exit(0);
  }

  console.log("🎤  Voice Emotion Samples Generator");
  console.log("   Free path: local rich SSML builder (textToRichSSML)");
  console.log("   Mock premium: basic SSML + simulated ElevenLabs voice_settings");
  console.log(`   Corpus size: ${corpus.length} samples\n`);

  const outputsDir = path.join(__dirname, "outputs");
  if (doWrite) {
    fs.mkdirSync(outputsDir, { recursive: true });
    console.log(`📁 Writing detailed outputs to: ${outputsDir}\n`);
  }

  const fullReportLines = [];
  fullReportLines.push("VOICE EMOTION SAMPLES — FULL A/B REPORT");
  fullReportLines.push(`Generated: ${new Date().toISOString()}`);
  fullReportLines.push(`Builder: api/ssml-builder.js (textToRichSSML + textToBasicSSML)`);
  fullReportLines.push(`Total samples: ${corpus.length}\n`);

  let richTriggeredEmotion = 0;
  let dialogueCount = 0;
  let totalExpressBoosts = 0;

  corpus.forEach((sample, idx) => {
    const num = String(idx + 1).padStart(2, "0");
    const { id, text, category, defaultStyle, defaultExpress, listeningNotes } = sample;

    const style = defaultStyle || "auto";
    const expr = defaultExpress || 0.78;

    const rich = textToRichSSML(text, { style, expressiveness: expr });
    const basic = textToBasicSSML ? textToBasicSSML(text) : `<prosody>${text}</prosody>`;
    const mockPremium = mockElevenLabsSettings(style, expr);

    if (rich.includes("mstts:express-as")) richTriggeredEmotion++;
    if (rich.includes("role=\"")) dialogueCount++;
    if (expr > 0.7) totalExpressBoosts++;

    printSection(`${num}. ${id} [${category || style}]`);
    console.log("TEXT:", text.slice(0, 160) + (text.length > 160 ? "..." : ""));
    console.log("\nFREE RICH SSML:");
    console.log(truncateForConsole(rich));
    console.log("\nBASIC SSML:");
    console.log(truncateForConsole(basic));
    console.log(`\nMOCK PREMIUM SETTINGS: ${JSON.stringify(mockPremium)}`);
    console.log("\nLISTENING NOTES:", listeningNotes || "Compare rich vs basic for warmth, pacing, and character.");

    if (doWrite) {
      fs.writeFileSync(path.join(outputsDir, `${num}-${id}-basic.ssml`), basic);
      fs.writeFileSync(path.join(outputsDir, `${num}-${id}-free.ssml`), rich);
      fs.writeFileSync(path.join(outputsDir, `${num}-${id}-report.txt`),
        `TEXT:\n${text}\n\nRICH:\n${rich}\n\nBASIC:\n${basic}\n\nPREMIUM: ${JSON.stringify(mockPremium)}\n\nNOTES: ${listeningNotes || ""}`);
    }

    fullReportLines.push(`\n========== ${num}. ${id} [${category || style}] ==========`);
    fullReportLines.push(`\nTEXT: ${text}\n`);
    fullReportLines.push(`FREE RICH SSML:\n${rich}\n`);
    fullReportLines.push(`BASIC SSML:\n${basic}\n`);
    fullReportLines.push(`MOCK PREMIUM SETTINGS: ${JSON.stringify(mockPremium)}`);
    fullReportLines.push(`LISTENING NOTES: ${listeningNotes || ""}\n`);
  });

  console.log("\n" + "=".repeat(78));
  console.log(`SUMMARY: ${richTriggeredEmotion}/${corpus.length} samples triggered rich emotion styles`);
  console.log(`         ${dialogueCount} samples got dialogue role attributes`);
  console.log(`         High-express runs: ${totalExpressBoosts}`);
  console.log("=".repeat(78));

  if (doWrite) {
    fs.writeFileSync(path.join(outputsDir, "FULL-REPORT.txt"), fullReportLines.join("\n"));
    console.log(`\n✅ Wrote FULL-REPORT.txt + per-sample files to ${outputsDir}`);
  }
}

run();
