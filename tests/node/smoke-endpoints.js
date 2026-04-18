"use strict";

const { test } = require("node:test");
const assert = require("node:assert/strict");
const voicesHandler = require("../../api/voices");
const healthHandler = require("../../api/health");
const launchHandler = require("../../api/launch");

function captureJsonResponse() {
  const state = { statusCode: 0, body: null, headers: {} };
  state.promise = new Promise((resolve) => (state.resolve = resolve));
  const res = {
    setHeader(k, v) { state.headers[k] = String(v); },
    status(code) { state.statusCode = code; return res; },
    json(obj) { state.body = obj; state.resolve(state); return res; },
  };
  return { res, state };
}

test("GET /api/voices returns ok with rich catalog", async () => {
  const { res, state } = captureJsonResponse();
  voicesHandler({ method: "GET" }, res);
  await state.promise;
  assert.equal(state.statusCode, 200);
  assert.equal(state.body.status, "ok");
  assert.ok(state.body.count > 10);
  assert.ok(state.body.voices.every((v) => v.id && v.label && v.locale));
  assert.ok(state.body.voices.some((v) => v.id === state.body.default));
});

test("GET /api/health returns ok", async () => {
  const { res, state } = captureJsonResponse();
  healthHandler({ method: "GET" }, res);
  await state.promise;
  assert.equal(state.statusCode, 200);
  assert.equal(state.body.status, "ok");
});

test("GET /api/launch documents tts endpoint", async () => {
  const { res, state } = captureJsonResponse();
  launchHandler({ method: "GET" }, res);
  await state.promise;
  assert.equal(state.statusCode, 200);
  assert.ok(Array.isArray(state.body.steps));
  assert.ok(state.body.tts_endpoint);
});
