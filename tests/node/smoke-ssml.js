"use strict";

const { test } = require("node:test");
const assert = require("node:assert/strict");

const { textToRichSSML } = require("../../api/ssml-builder.js");
const { voiceSupportsStyle, getVoiceMeta } = require("../../api/_voices.js");

const SAD_TEXT =
  "She wept with grief and sorrow. Heartbroken and lonely, she mourned her loss.";

function styles(ssml) {
  return (ssml.match(/style="([^"]+)"/g) || []).map((s) =>
    s.replace(/^style="/, "").replace(/"$/, "")
  );
}

test("Multilingual flagship voice (Ava) emits NO express-as (prosody-only path)", () => {
  const ssml = textToRichSSML(SAD_TEXT, {
    voice: "en-US-AvaMultilingualNeural",
    expressiveness: 0.92,
    style: "auto",
  });
  assert.ok(ssml.length > 0, "ssml should be non-empty");
  assert.ok(!ssml.includes("mstts:express-as"), "Ava must not contain express-as");
  assert.ok(ssml.startsWith("<speak"), "must start with <speak");
  assert.ok(ssml.trim().endsWith("</speak>"), "must end with </speak>");
  // Prosody work must still be present.
  assert.ok(ssml.includes("<prosody"), "should still have prosody");
});

test("Aria with sad text emits express-as with a style Aria supports", () => {
  const ssml = textToRichSSML(SAD_TEXT, {
    voice: "en-US-AriaNeural",
    expressiveness: 0.9,
    style: "auto",
  });
  assert.ok(ssml.includes("mstts:express-as"), "Aria should use express-as");
  const used = styles(ssml);
  assert.ok(used.length > 0, "should emit at least one style");
  for (const s of used) {
    assert.ok(
      voiceSupportsStyle("en-US-AriaNeural", s),
      `Aria must support emitted style "${s}"`
    );
  }
  assert.ok(used.includes("sad"), "expected a sad-family style for sad text");
});

test("output never contains role= for an en-US standard voice", () => {
  const voices = [
    "en-US-AriaNeural",
    "en-US-GuyNeural",
    "en-US-JennyNeural",
    "en-US-DavisNeural",
  ];
  for (const v of voices) {
    const ssml = textToRichSSML('"How dare you!" she shouted, furious and enraged.', {
      voice: v,
      expressiveness: 0.9,
      style: "auto",
      isDialogue: true,
    });
    assert.ok(!ssml.includes("role="), `${v} must not emit role=`);
  }
});

test("output is always wrapped in <speak> and non-empty across voices", () => {
  const voices = [
    "en-US-AvaMultilingualNeural",
    "en-US-AriaNeural",
    "en-GB-SoniaNeural",
    "fr-FR-DeniseNeural",
    "zh-CN-XiaoxiaoNeural",
  ];
  for (const v of voices) {
    const ssml = textToRichSSML("Hello there, this is a calm sentence.", {
      voice: v,
      expressiveness: 0.7,
    });
    assert.ok(ssml.length > 0, `${v} ssml non-empty`);
    assert.ok(ssml.startsWith("<speak"), `${v} starts with <speak`);
    assert.ok(ssml.trim().endsWith("</speak>"), `${v} ends with </speak>`);
  }
});

test("unknown / missing voice never emits express-as (safe path)", () => {
  const a = textToRichSSML(SAD_TEXT, { expressiveness: 0.95, style: "auto" });
  const b = textToRichSSML(SAD_TEXT, {
    voice: "en-XX-NotARealVoice",
    expressiveness: 0.95,
    style: "auto",
  });
  assert.ok(!a.includes("mstts:express-as"), "missing voice => no express-as");
  assert.ok(!b.includes("mstts:express-as"), "unknown voice => no express-as");
});

test("voiceSupportsStyle works for known cases", () => {
  assert.equal(voiceSupportsStyle("en-US-AriaNeural", "sad"), true);
  assert.equal(voiceSupportsStyle("en-US-AriaNeural", "narration-professional"), true);
  assert.equal(voiceSupportsStyle("en-US-AvaMultilingualNeural", "sad"), false);
  assert.equal(voiceSupportsStyle("en-US-AvaMultilingualNeural", "cheerful"), false);
  assert.equal(voiceSupportsStyle("en-US-GuyNeural", "newscast"), true);
  assert.equal(voiceSupportsStyle("en-US-GuyNeural", "assistant"), false);
  assert.equal(voiceSupportsStyle("nope", "sad"), false);
});

test("getVoiceMeta returns object or null", () => {
  const ava = getVoiceMeta("en-US-AvaMultilingualNeural");
  assert.ok(ava && ava.id === "en-US-AvaMultilingualNeural");
  assert.equal(ava.supportsExpressAs, false);
  assert.ok(Array.isArray(ava.styles) && ava.styles.length === 0);
  assert.equal(getVoiceMeta("does-not-exist"), null);
  assert.equal(getVoiceMeta(null), null);
});
