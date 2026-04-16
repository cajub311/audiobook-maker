function buildBaseUrl(req) {
  const forwardedProto = req && req.headers ? req.headers["x-forwarded-proto"] : null;
  const host = req && req.headers ? req.headers.host : null;
  if (!host) {
    return "";
  }
  const proto = String(forwardedProto || "https").split(",")[0].trim() || "https";
  return `${proto}://${host}`;
}

module.exports = function handler(req, res) {
  const baseUrl = buildBaseUrl(req);
  const configuredGradioUrl = String(process.env.GRADIO_SERVER_URL || "").trim();
  const launcherUrl = baseUrl ? `${baseUrl}/web/index.html` : "/web/index.html";
  const openUrl = configuredGradioUrl || "http://localhost:7860";

  res.setHeader("Content-Type", "application/json; charset=utf-8");
  res.status(200).json({
    project: "audiobook-maker",
    purpose: "Launch metadata for audiobook launcher + Python Gradio app.",
    launcher_url: launcherUrl,
    gradio_url: configuredGradioUrl || null,
    open_url: openUrl,
    launch_mode: configuredGradioUrl ? "remote-gradio" : "local-gradio",
    steps: [
      "Install dependencies: pip install -r requirements.txt",
      "Start app: python3 audiobook_creator_v7.py",
      `Open ${openUrl} in your browser`,
      "Use Easy Mobile Mode tab for fastest setup (one-button flow)",
      "Optional: use System tab for free cloud manifest backup/restore"
    ],
    web_demo: "/web/index.html",
    note: "Use python on systems where python3 is not available.",
    health_endpoint: "/api/health",
    process_endpoint: "/api/process",
    process_usage: {
      start: "POST /api/process with { text, demoMode }",
      poll: "GET /api/process?job_id=<id>",
    }
  });
};
