const CACHE_NAME = "audiobook-launcher-v5";
const APP_SHELL = [
  "/",
  "/index.html",
  "/website/index.html",
  "/web/index.html",
  "/web/processor.js",
  "/web/api-client.js",
  "/web/storage.js",
  "/manifest.webmanifest",
  "/icon.svg",
  "/assets/gradio-ui-preview.svg",
  "/api/launch"
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(APP_SHELL))
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key))
      )
    )
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  if (event.request.method !== "GET") return;

  const url = new URL(event.request.url);
  if (event.request.mode === "navigate") {
    event.respondWith(
      fetch(event.request)
        .then((response) => {
          const copy = response.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put("/index.html", copy));
          return response;
        })
        .catch(() => caches.match("/index.html"))
    );
    return;
  }

  if (url.pathname.startsWith("/api/")) {
    if (url.pathname === "/api/launch") {
      event.respondWith(
        fetch(event.request).catch(() => caches.match("/api/launch"))
      );
      return;
    }
    if (url.pathname === "/api/health" || url.pathname === "/api/process") {
      event.respondWith(
        fetch(event.request).catch(
          () =>
            new Response(JSON.stringify({ ok: false, error: "offline" }), {
              status: 503,
              headers: { "Content-Type": "application/json; charset=utf-8" },
            })
        )
      );
      return;
    }
    event.respondWith(
      fetch(event.request)
    );
    return;
  }

  event.respondWith(
    caches.match(event.request).then((cached) => {
      if (cached) return cached;
      return fetch(event.request).then((response) => {
        const copy = response.clone();
        if (response && response.ok) {
          caches.open(CACHE_NAME).then((cache) => cache.put(event.request, copy));
        }
        return response;
      });
    })
  );
});
