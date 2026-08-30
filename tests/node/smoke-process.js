"use strict";

const { test } = require("node:test");
const assert = require("node:assert/strict");
const handler = require("../../api/process");

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
    status(code) { state.statusCode = code; return res; },
    json(obj) {
      state.body = obj;
      state.kind = "json";
      state.ended = true;
      state.resolve(state);
      return res;
    },
    end() {
      state.kind = "end";
      state.ended = true;
      state.resolve(state);
      return res;
    },
  };
  return { res, state };
}

test("process: rejects empty POST body", async () => {
  const { res, state } = makeResponseMock();
  await handler({ method: "POST", body: { text: "   " } }, res);
  await state.promise;
  assert.equal(state.statusCode, 400);
  assert.equal(state.body.status, "error");
});

test("process: accepts POST and returns job_id", async () => {
  const { res, state } = makeResponseMock();
  await handler({ method: "POST", body: { text: "Hello audiobook world." } }, res);
  await state.promise;
  assert.equal(state.statusCode, 202);
  assert.equal(state.body.status, "queued");
  assert.match(state.body.job_id, /^job_/);
  assert.match(state.body.poll_url, /job_id=/);
});

test("process: GET poll returns progress for known job", async () => {
  const { res: postRes, state: postState } = makeResponseMock();
  await handler({ method: "POST", body: { text: "Poll me." } }, postRes);
  await postState.promise;
  const jobId = postState.body.job_id;

  const { res, state } = makeResponseMock();
  await handler({ method: "GET", query: { job_id: jobId } }, res);
  await state.promise;
  assert.equal(state.statusCode, 200);
  assert.equal(state.body.job_id, jobId);
  assert.ok(typeof state.body.progress_percent === "number");
});

test("process: GET without job_id returns 400", async () => {
  const { res, state } = makeResponseMock();
  await handler({ method: "GET", query: {} }, res);
  await state.promise;
  assert.equal(state.statusCode, 400);
});

test("process: OPTIONS returns 204", async () => {
  const { res, state } = makeResponseMock();
  await handler({ method: "OPTIONS" }, res);
  await state.promise;
  assert.equal(state.statusCode, 204);
});
