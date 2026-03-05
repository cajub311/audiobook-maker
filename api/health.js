module.exports = function handler(_req, res) {
  res.setHeader("Content-Type", "application/json; charset=utf-8");
  res.status(200).json({
    status: "ok",
    service: "audiobook-launcher",
    timestamp: new Date().toISOString()
  });
};
