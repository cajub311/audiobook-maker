"use strict";

const { test } = require("node:test");
const assert = require("node:assert/strict");

// The web chunker is ESM; we import it via dynamic import.
let chunkText;
test.before(async () => {
  const mod = await import("../../web/chunker.js");
  chunkText = mod.chunkText;
});

test("chunkText splits on paragraphs and stays under limit", () => {
  const para = "The quick brown fox jumps over the lazy dog. ".repeat(30);
  const text = [para, para, para].join("\n\n");
  const chunks = chunkText(text, 500);
  assert.ok(chunks.length >= 3, "expected multiple chunks for long text");
  for (const c of chunks) {
    assert.ok(c.length <= 500, `chunk exceeds limit: ${c.length}`);
    assert.ok(c.length > 0);
  }
  assert.ok(chunks.join(" ").replace(/\s+/g, " ").length >= text.replace(/\s+/g, " ").length * 0.9);
});

test("chunkText returns [] for empty input", () => {
  assert.deepEqual(chunkText(""), []);
  assert.deepEqual(chunkText("   "), []);
});

test("chunkText keeps short text as one chunk", () => {
  const chunks = chunkText("Hello world. This is a short story.");
  assert.equal(chunks.length, 1);
});

test("chunkText hard-splits extremely long sentences", () => {
  const longSentence = "word ".repeat(1000).trim() + ".";
  const chunks = chunkText(longSentence, 400);
  assert.ok(chunks.length > 1);
  for (const c of chunks) assert.ok(c.length <= 400);
});
