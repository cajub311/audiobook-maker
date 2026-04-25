"use strict";

const { test } = require("node:test");
const assert = require("node:assert/strict");
const processHandler = require("../../api/process");

function captureJsonResponse() {
  const state = { statusCode: 0, body: null, headers: {} };
  state.promise = new Promise((resolve) => (state.resolve = resolve));
  const res = {
    setHeader(k, v) {
      state.headers[k] = String(v);
    },
    status(code) {
      state.statusCode = code;
      return res;
    },
    json(obj) {
      state.body = obj;
      state.resolve(state);
      return res;
    },
  };
  return { res, state };
}

test("POST /api/process accepts text and returns poll_url", async () => {
  const { res, state } = captureJsonResponse();
  await processHandler(
    { method: "POST", body: { text: "Hello demo world.", demoMode: true } },
    res,
  );
  await state.promise;
  assert.equal(state.statusCode, 202);
  assert.equal(state.body.status, "queued");
  assert.ok(state.body.job_id);
  assert.ok(String(state.body.poll_url || "").includes("job_id="));
  assert.ok(state.body.note.toLowerCase().includes("poll"));
});

test("POST /api/process rejects oversized body", async () => {
  const { res, state } = captureJsonResponse();
  const huge = "x".repeat(400_001);
  await processHandler({ method: "POST", body: { text: huge } }, res);
  await state.promise;
  assert.equal(state.statusCode, 413);
  assert.equal(state.body.status, "error");
});

test("GET /api/process returns progress for known job", async () => {
  const post = captureJsonResponse();
  await processHandler({ method: "POST", body: { text: "abc" } }, post.res);
  await post.state.promise;
  const jobId = post.state.body.job_id;

  const get = captureJsonResponse();
  await processHandler({ method: "GET", query: { job_id: jobId } }, get.res);
  await get.state.promise;
  assert.equal(get.state.statusCode, 200);
  assert.ok(["queued", "processing", "completed"].includes(get.state.body.status));
});

test("GET /api/process 404 for unknown job", async () => {
  const { res, state } = captureJsonResponse();
  await processHandler({ method: "GET", query: { job_id: "job_missing_xyz" } }, res);
  await state.promise;
  assert.equal(state.statusCode, 404);
});
