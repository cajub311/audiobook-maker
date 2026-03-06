module.exports = async function handler(req, res) {
  res.setHeader("Content-Type", "application/json; charset=utf-8");

  if (req.method !== "POST") {
    res.status(405).json({ status: "error", message: "Use POST for /api/process." });
    return;
  }

  // Phase placeholder for hosted async processing.
  res.status(501).json({
    status: "not_implemented",
    message: "Cloud processing endpoint is planned but not enabled yet.",
    next_steps: [
      "Deploy Python backend worker for async jobs",
      "Persist jobs in queue/storage",
      "Return job_id and polling/webhook URLs",
    ],
  });
};
