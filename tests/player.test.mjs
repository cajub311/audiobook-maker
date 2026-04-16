// Node smoke tests for the browser player engine.
// Run with: node tests/player.test.mjs
import assert from "node:assert/strict";
import { splitChapters, splitSentences, buildAudiobook } from "../web/player.js";

const sample = `Chapter 1: The Start\n\nHello world. This is the first sentence! And this is the second?\n\nChapter 2: The Middle\n\n"Hi," she said. "How are you?" They walked on.`;

const chapters = splitChapters(sample);
assert.equal(chapters.length, 2, "expected two chapters");
assert.match(chapters[0].title, /Chapter 1/);
assert.match(chapters[1].title, /Chapter 2/);

const sentences = splitSentences(chapters[0].body);
assert.ok(sentences.length >= 3, `expected at least 3 sentences in first chapter, got ${sentences.length}`);
assert.ok(sentences[0].toLowerCase().includes("hello"));

const longBody = "word ".repeat(300);
const capped = splitSentences(longBody);
assert.ok(capped.every((s) => s.length <= 281), "long runs should be hard-capped");

const book = buildAudiobook(sample);
assert.ok(book.totalChars > 0);
assert.ok(book.totalSentences >= 4);
assert.equal(book.chapters.length, 2);

const emptyBook = buildAudiobook("");
assert.equal(emptyBook.chapters.length, 0, "empty text should produce no chapters");

const fallback = splitChapters("Just a single paragraph with no chapter markers at all. This should still produce one section.");
assert.equal(fallback.length, 1, "text without markers should fall back to one section");

console.log("player.test.mjs ok");
