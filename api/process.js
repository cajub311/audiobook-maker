const JOBS = global.__abm_process_jobs || new Map();
global.__abm_process_jobs = JOBS;
const JOB_TTL_AFTER_COMPLETE_MS = 5 * 60 * 1000;

function safeBody(req) {
  if (!req || req.body == null) return {};
  if (typeof req.body === "object") return req.body;
  try {
    return JSON.parse(req.body);
  } catch (_err) {
    return {};
  }
}

function projectStatus(job) {
  const elapsedMs = Date.now() - job.createdAt;
  const progress = Math.min(100, Math.floor((elapsedMs / Math.max(1000, job.targetMs)) * 100));
  const status = progress >= 100 ? "completed" : progress < 10 ? "queued" : "processing";
  const etaMs = Math.max(0, job.targetMs - elapsedMs);
  return { progress, status, etaMs };
}

function createJobId() {
  return `job_${Date.now().toString(36)}_${Math.random().toString(36).slice(2)}`;
}

module.exports = async function handler(req, res) {
  res.setHeader("Content-Type", "application/json; charset=utf-8");

  if (req.method === "GET") {
    const jobId = String((req.query && (req.query.job_id || req.query.jobId)) || "");
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

  if (req.method === "POST") {
    const body = safeBody(req);
    const text = String(body.text || "");
    const demoMode = Boolean(body.demoMode);
    if (!text.trim()) {
      res.status(400).json({ status: "error", message: "Provide non-empty text in request body." });
      return;
    }

    const jobId = createJobId();
    const chars = text.length;
    const cps = 28; // edge-like estimate for non-demo estimates
    // Demo jobs only drive UI progress; keep duration short so the web client
    // (which polls for ~24–30s) reliably sees "completed" instead of timing out.
    const estMs = demoMode
      ? Math.min(14000, Math.max(900, Math.floor(chars * 1.2)))
      : Math.max(4000, Math.min(180000, Math.floor((chars / cps) * 1000)));
    const createdAt = Date.now();
    JOBS.set(jobId, {
      createdAt,
      targetMs: estMs,
      textChars: chars,
      demoMode,
    });
    const cleanupDelayMs = estMs + JOB_TTL_AFTER_COMPLETE_MS;
    const cleanupTimer = setTimeout(() => {
      JOBS.delete(jobId);
    }, cleanupDelayMs);
    if (typeof cleanupTimer.unref === "function") {
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
};
