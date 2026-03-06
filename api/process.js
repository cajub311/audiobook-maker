const JOBS = global.__abm_process_jobs || new Map();
global.__abm_process_jobs = JOBS;

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

    const jobId = `job_${Date.now().toString(36)}${Math.random().toString(36).slice(2)}`;
    const chars = text.length;
    const cps = 28; // edge-like estimate
    const estMs = Math.max(4000, Math.min(180000, Math.floor((chars / cps) * 1000)));
    JOBS.set(jobId, {
      createdAt: Date.now(),
      targetMs: estMs,
      textChars: chars,
      demoMode,
    });
    // Clean up completed job after 5 minutes to prevent memory accumulation
    setTimeout(() => JOBS.delete(jobId), estMs + 300000);

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
