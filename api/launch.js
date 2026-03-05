module.exports = function handler(req, res) {
  res.setHeader("Content-Type", "application/json; charset=utf-8");
  res.status(200).json({
    project: "audiobook-maker",
    purpose: "Launcher instructions for the Python Gradio app.",
    steps: [
      "Install dependencies: pip install -r requirements.txt",
      "Start app: python3 audiobook_creator_v7.py",
      "Open http://localhost:7860 in your browser"
    ],
    note: "Use python on systems where python3 is not available."
  });
};
