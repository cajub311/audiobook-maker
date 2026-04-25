"use strict";

const { test } = require("node:test");
const assert = require("node:assert/strict");

let splitChapters;
let splitIntoChunks;
let detectSpeakers;
let extractCastOrdered;

test.before(async () => {
  const mod = await import("../../web/text.js");
  splitChapters = mod.splitChapters;
  splitIntoChunks = mod.splitIntoChunks;
  detectSpeakers = mod.detectSpeakers;
  extractCastOrdered = mod.extractCastOrdered;
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

test("extractCastOrdered picks Mark Thompson then Sarah from italics + speech", () => {
  const text = `Mark Thompson had stopped.

But tonight: *Sarah calling.*

"Mark?"

"I'm still here," she said. "In the dark."`;
  const cast = extractCastOrdered(text);
  assert.ok(cast.includes("Mark Thompson") || cast.includes("Mark"));
  assert.ok(cast.some((n) => String(n).includes("Sarah")));
});

test("chained quote after she said attributes to same speaker (Sarah)", () => {
  const text = `Sarah waited by the door.

"I'm still here," she said. "In the dark."`;
  const chunks = splitIntoChunks(splitChapters(text));
  const lines = chunks.filter((c) => c.isDialogue).map((c) => ({ t: c.text, sp: c.speaker }));
  assert.equal(lines[0].sp, "Sarah");
  assert.equal(lines[1].sp, "Sarah");
});

test("Name-only question addressee: Mark? spoken by other cast member", () => {
  const text = `Mark Thompson walked in.

Sarah frowned.

"Mark?"`;
  const chunks = splitIntoChunks(splitChapters(text));
  const markQ = chunks.find((c) => c.isDialogue && c.text.includes("Mark"));
  assert.ok(markQ);
  assert.equal(markQ.speaker, "Sarah");
});
