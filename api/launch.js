function trimTrailingSlash(u) {
  if (!u) return "";
  return u.replace(/\/+$/, "");
}

module.exports = function handler(req, res) {
  res.setHeader("Content-Type", "application/json; charset=utf-8");

  const gradioUrl = trimTrailingSlash(
    String(process.env.GRADIO_SERVER_URL || process.env.HF_SPACE_URL || "").trim()
  );
  const launcherUrl = trimTrailingSlash(
    String(process.env.LAUNCHER_PUBLIC_URL || process.env.VERCEL_URL || "").trim()
  );
  const resolvedLauncher =
    launcherUrl && !/^https?:\/\//i.test(launcherUrl)
      ? `https://${launcherUrl}`
      : launcherUrl;

  const payload = {
    project: "audiobook-maker",
    purpose: "Launcher instructions for the Python Gradio app.",
    steps: [
      "Install dependencies: pip install -r requirements.txt",
      "Start app: python3 audiobook_creator_v7.py",
      "Open http://localhost:7860 in your browser",
      "Use Easy Mobile Mode tab for fastest setup (one-button flow)",
      "Optional: use System tab for free cloud manifest backup/restore"
    ],
    launcher_page: "/",
    web_demo: "/web/index.html",
    note: "Use python on systems where python3 is not available.",
    health_endpoint: "/api/health",
    process_endpoint: "/api/process",
    process_usage: {
      start: "POST /api/process with { text, demoMode }",
      poll: "GET /api/process?job_id=<id>"
    }
  };

  if (gradioUrl) {
    payload.gradio_app_url = gradioUrl;
    payload.open_app = gradioUrl;
  }
  if (resolvedLauncher) {
    payload.static_launcher_url = resolvedLauncher;
  }

  res.status(200).json(payload);
};
