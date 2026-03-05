module.exports = function handler(req, res) {
  res.setHeader("Content-Type", "application/json; charset=utf-8");
  res.status(200).json({
    project: "audiobook-maker",
    purpose: "Launcher instructions for the Python Gradio app.",
    steps: [
      "Install dependencies: pip install -r requirements.txt",
      "Start app: python app.py",
      "Open the Gradio URL printed in your terminal"
    ],
    note: "If your entrypoint script is not app.py, run your actual Gradio script instead."
  });
};
