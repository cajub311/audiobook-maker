"use strict";

const { test } = require("node:test");
const assert = require("node:assert/strict");

let splitChapters;
let splitIntoChunks;
let detectSpeakers;

test.before(async () => {
  const mod = await import("../../web/text.js");
  splitChapters = mod.splitChapters;
  splitIntoChunks = mod.splitIntoChunks;
  detectSpeakers = mod.detectSpeakers;
});

test("splitChapters detects Chapter headings", () => {
  const text = "Chapter 1\nHello.\n\nChapter 2\nWorld.";
  const chapters = splitChapters(text);
  assert.equal(chapters.length, 2);
  assert.equal(chapters[0].title, "Chapter 1");
  assert.equal(chapters[1].title, "Chapter 2");
});

test("splitIntoChunks separates dialogue from narration", () => {
  const chapters = splitChapters('Chapter 1\n"Hello," Alice said. Then she ran.');
  const chunks = splitIntoChunks(chapters);
  const dialogue = chunks.filter((c) => c.isDialogue);
  const narration = chunks.filter((c) => !c.isDialogue);
  assert.ok(dialogue.length >= 1, "expected at least one dialogue chunk");
  assert.ok(narration.length >= 1, "expected at least one narration chunk");
});

test("detectSpeakers returns named speakers and ignores pronouns", () => {
  const text = `Chapter 1
"Hi," Alice said.
"Hello back," Bob answered.
"Run!" she shouted.
"Why?" he whispered.
Bob laughed.
"Because," Alice said.`;
  const chunks = splitIntoChunks(splitChapters(text));
  const speakers = detectSpeakers(chunks);
  const names = speakers.map((s) => s.name);
  assert.ok(names.includes("Alice"));
  assert.ok(names.includes("Bob"));
  assert.ok(!names.includes("He"));
  assert.ok(!names.includes("She"));
});

test("detectSpeakers handles Name: before quote", () => {
  const text = `Chapter 1
Sarah: "We should leave now."
Tom: "I agree."`;
  const chunks = splitIntoChunks(splitChapters(text));
  const speakers = detectSpeakers(chunks);
  const names = speakers.map((s) => s.name);
  assert.ok(names.includes("Sarah"));
  assert.ok(names.includes("Tom"));
});

test("detectSpeakers handles em dash after quote", () => {
  const text = `"Wait up." — Marcus
"Coming." — Elena`;
  const chunks = splitIntoChunks(splitChapters(text));
  const speakers = detectSpeakers(chunks);
  const names = speakers.map((s) => s.name);
  assert.ok(names.includes("Marcus"));
  assert.ok(names.includes("Elena"));
});

test("unattributed alternating quotes get Speaker A and B", () => {
  const text = `"Hello there."
"Hi yourself."
"Nice day."
"Sure is."`;
  const chunks = splitIntoChunks(splitChapters(text));
  const speakers = detectSpeakers(chunks);
  const names = new Set(speakers.map((s) => s.name));
  assert.ok(names.has("Speaker A"));
  assert.ok(names.has("Speaker B"));
});
