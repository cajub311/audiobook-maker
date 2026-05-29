#!/usr/bin/env node
"use strict";

const http = require("http");
const fs = require("fs");
const path = require("path");
const url = require("url");

const PORT = Number(process.env.PORT) || 8002;
const ROOT = path.resolve(__dirname, "..");

const handlers = {
  "/api/tts": require(path.join(ROOT, "api/tts")),
  "/api/voices": require(path.join(ROOT, "api/voices")),
  "/api/health": require(path.join(ROOT, "api/health")),
  "/api/launch": require(path.join(ROOT, "api/launch")),
  "/api/process": require(path.join(ROOT, "api/process")),
  "/api/elevenlabs": require(path.join(ROOT, "api/elevenlabs")),
};

function mimeOf(p) {
  if (p.endsWith(".html")) return "text/html; charset=utf-8";
  if (p.endsWith(".js") || p.endsWith(".mjs")) return "application/javascript; charset=utf-8";
  if (p.endsWith(".css")) return "text/css; charset=utf-8";
  if (p.endsWith(".svg")) return "image/svg+xml";
  if (p.endsWith(".json")) return "application/json; charset=utf-8";
  if (p.endsWith(".webmanifest")) return "application/manifest+json";
  return "application/octet-stream";
}

function shimResponse(res) {
  if (!res.status) {
    res.status = function (code) {
      this.statusCode = code;
      return this;
    };
  }
  if (!res.json) {
    res.json = function (obj) {
      if (!this.getHeader("Content-Type")) {
        this.setHeader("Content-Type", "application/json; charset=utf-8");
      }
      this.end(JSON.stringify(obj));
      return this;
    };
  }
  return res;
}

const server = http.createServer(async (req, res) => {
  shimResponse(res);
  const parsed = url.parse(req.url, true);
  const pathname = parsed.pathname;
  if (handlers[pathname]) {
    let body = "";
    req.on("data", (c) => (body += c));
    req.on("end", () => {
      try {
        req.body = body ? JSON.parse(body) : undefined;
      } catch (_e) {
        req.body = body;
      }
      req.query = parsed.query;
      try {
        const out = handlers[pathname](req, res);
        if (out && typeof out.catch === "function") {
          out.catch((err) => {
            console.error("handler error:", err);
            try {
              res.writeHead(500, { "Content-Type": "application/json" });
              res.end(JSON.stringify({ error: String(err) }));
            } catch (_e) {
              // response may already be written
            }
          });
        }
      } catch (err) {
        console.error(err);
        try {
          res.writeHead(500, { "Content-Type": "application/json" });
          res.end(JSON.stringify({ error: String(err) }));
        } catch (_e) {
          // response may already be written
        }
      }
    });
    return;
  }
  const file = pathname === "/" ? "/index.html" : pathname;
  const full = path.join(ROOT, file);
  if (!full.startsWith(ROOT)) {
    res.writeHead(403).end();
    return;
  }
  fs.stat(full, (err, stat) => {
    if (err || !stat.isFile()) {
      res.writeHead(404).end("not found");
      return;
    }
    res.writeHead(200, { "Content-Type": mimeOf(full), "Content-Length": stat.size });
    fs.createReadStream(full).pipe(res);
  });
});
server.listen(PORT, () => console.log(`[dev-server] listening on http://127.0.0.1:${PORT}`));
