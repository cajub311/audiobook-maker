"use strict";

const { test } = require("node:test");
const assert = require("node:assert/strict");
const handler = require("../../api/tts");
const { VOICES, DEFAULT_VOICE } = require("../../api/_voices");

function makeResponseMock() {
  const headers = {};
  const state = {
    statusCode: 0,
    headers,
    body: null,
    kind: null,
    ended: false,
    promise: null,
  };
  state.promise = new Promise((resolve) => {
    state.resolve = resolve;
  });
  const res = {
    setHeader(k, v) { headers[k] = String(v); },
    getHeader(k) { return headers[k]; },
    status(code) { state.statusCode = code; return res; },
    json(obj) {
      state.body = obj;
      state.kind = "json";
      state.ended = true;
      state.resolve(state);
      return res;
    },
    send(buf) {
      state.body = buf;
      state.kind = "bytes";
      state.ended = true;
      state.resolve(state);
      return res;
    },
    end(buf) {
      if (buf != null) state.body = buf;
      state.kind = state.kind || "bytes";
      state.ended = true;
      state.resolve(state);
      return res;
    },
  };
  return { res, state };
}

test("voices list is non-empty and default is in the list", () => {
  assert.ok(Array.isArray(VOICES));
  assert.ok(VOICES.length >= 10, "expect a rich voice catalog");
  assert.ok(VOICES.some((v) => v.id === DEFAULT_VOICE));
  for (const voice of VOICES) {
    assert.equal(typeof voice.id, "string");
    assert.match(voice.id, /Neural$/);
    assert.equal(typeof voice.label, "string");
    assert.equal(typeof voice.locale, "string");
  }
});

test("tts: rejects non-POST", async () => {
  const { res, state } = makeResponseMock();
  await handler({ method: "GET" }, res);
  await state.promise;
  assert.equal(state.statusCode, 405);
  assert.equal(state.kind, "json");
});

test("tts: rejects empty text", async () => {
  const { res, state } = makeResponseMock();
  await handler({ method: "POST", body: { text: "" } }, res);
  await state.promise;
  assert.equal(state.statusCode, 400);
  assert.equal(state.kind, "json");
});

test("tts: rejects oversized text", async () => {
  const { res, state } = makeResponseMock();
  const bigText = "a".repeat(handler.MAX_CHARS + 1);
  await handler({ method: "POST", body: { text: bigText } }, res);
  await state.promise;
  assert.equal(state.statusCode, 413);
  assert.equal(state.kind, "json");
  assert.equal(state.body.max_chars, handler.MAX_CHARS);
});

test("tts: preflight CORS", async () => {
  const { res, state } = makeResponseMock();
  await handler({ method: "OPTIONS" }, res);
  await state.promise;
  assert.equal(state.statusCode, 204);
  assert.ok(state.headers["Access-Control-Allow-Origin"]);
});

test("xmlEscape: escapes problematic characters", () => {
  const out = handler.xmlEscape(`<hello & "world">`);
  assert.equal(out, "&lt;hello &amp; &quot;world&quot;&gt;");
});

test("clampRate and formatRateAsPercent produce valid SSML rate strings", () => {
  assert.equal(handler.clampRate(0.1), 0.1);
  assert.equal(handler.clampRate(2), 0.5);
  assert.equal(handler.clampRate(-2), -0.5);
  assert.equal(handler.formatRateAsPercent(0), "+0%");
  assert.equal(handler.formatRateAsPercent(0.25), "+25%");
  assert.equal(handler.formatRateAsPercent(-0.1), "-10%");
});
