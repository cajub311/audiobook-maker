"use strict";

// Demo async-job simulator.
// Contract (relied on by clients):
//   POST -> 202 { status:"queued", job_id, poll_url, estimated_seconds, note }
//   GET ?job_id=... -> 200 { status, job_id, progress_percent, eta_seconds, demo_mode, text_chars }
//
// This is an in-memory simulator (no real audio work); jobs are kept in a
// process-global Map and self-expire. Hardened for malformed input and never
// throws uncaught.

const JOBS = global.__abm_process_jobs || new Map();
global.__abm_process_jobs = JOBS;

const JOB_TTL_AFTER_COMPLETE_MS = 5 * 60 * 1000;
const MAX_TEXT_CHARS = 2_000_000; // guard against absurd payloads
const MAX_JOBS = 5000; // soft cap to bound memory

function safeBody(req) {
  if (!req || req.body == null) return {};
  if (typeof req.body === "object") return req.body;
  try {
    const parsed = JSON.parse(req.body);
    return parsed && typeof parsed === "object" ? parsed : {};
  } catch (_err) {
    return {};
  }
}

function projectStatus(job) {
  const elapsedMs = Date.now() - job.createdAt;
  const targetMs = Math.max(1000, job.targetMs);
  const progress = Math.min(100, Math.max(0, Math.floor((elapsedMs / targetMs) * 100)));
  const status = progress >= 100 ? "completed" : progress < 10 ? "queued" : "processing";
  const etaMs = Math.max(0, job.targetMs - elapsedMs);
  return { progress, status, etaMs };
}

function createJobId() {
  return `job_${Date.now().toString(36)}_${Math.random().toString(36).slice(2)}`;
}

module.exports = async function handler(req, res) {
  try {
    res.setHeader("Content-Type", "application/json; charset=utf-8");
    res.setHeader("Cache-Control", "no-store, max-age=0");

    const method = req && req.method;

    if (method === "OPTIONS") {
      res.status(204).end();
      return;
    }

    if (method === "GET") {
      const rawId = (req.query && (req.query.job_id || req.query.jobId)) || "";
      const jobId = String(rawId).slice(0, 200);
      if (!jobId) {
        res.status(400).json({ status: "error", message: "Missing query parameter: job_id" });
        return;
      }
      const job = JOBS.get(jobId);
      if (!job) {
        res.status(404).json({ status: "error", message: "Job not found." });
        return;
      }
      const state = projectStatus(job);
      res.status(200).json({
        status: state.status,
        job_id: jobId,
        progress_percent: state.progress,
        eta_seconds: Math.ceil(state.etaMs / 1000),
        demo_mode: !!job.demoMode,
        text_chars: job.textChars,
      });
      return;
    }

    if (method === "POST") {
      const body = safeBody(req);
      const text = typeof body.text === "string" ? body.text : String(body.text == null ? "" : body.text);
      const demoMode = Boolean(body.demoMode);

      if (!text.trim()) {
        res.status(400).json({ status: "error", message: "Provide non-empty text in request body." });
        return;
      }
      if (text.length > MAX_TEXT_CHARS) {
        res.status(413).json({
          status: "error",
          message: `Text too long (max ${MAX_TEXT_CHARS} chars).`,
        });
        return;
      }

      // Bound memory: if the map grows too large, drop the oldest entries.
      if (JOBS.size >= MAX_JOBS) {
        const oldest = JOBS.keys().next().value;
        if (oldest !== undefined) JOBS.delete(oldest);
      }

      const jobId = createJobId();
      const chars = text.length;
      const cps = 28; // edge-like throughput estimate
      const estMs = Math.max(4000, Math.min(180000, Math.floor((chars / cps) * 1000)));
      const createdAt = Date.now();

      JOBS.set(jobId, { createdAt, targetMs: estMs, textChars: chars, demoMode });

      const cleanupDelayMs = estMs + JOB_TTL_AFTER_COMPLETE_MS;
      const cleanupTimer = setTimeout(() => {
        JOBS.delete(jobId);
      }, cleanupDelayMs);
      if (cleanupTimer && typeof cleanupTimer.unref === "function") {
        cleanupTimer.unref();
      }

      res.status(202).json({
        status: "queued",
        job_id: jobId,
        poll_url: `/api/process?job_id=${encodeURIComponent(jobId)}`,
        estimated_seconds: Math.ceil(estMs / 1000),
        note: "Demo async job accepted. Check poll_url for progress.",
      });
      return;
    }

    res.status(405).json({ status: "error", message: "Use POST to start and GET to poll /api/process." });
  } catch (err) {
    try {
      res.setHeader("Content-Type", "application/json; charset=utf-8");
      res.status(500).json({ status: "error", message: "Internal error in /api/process." });
    } catch (_e) {
      /* response already sent */
    }
  }
};
