const CACHE_NAME = "audiobook-launcher-v6";
const APP_SHELL = [
  "/",
  "/index.html",
  "/web/",
  "/web/index.html",
  "/web/player.js",
  "/web/processor.js",
  "/web/api-client.js",
  "/web/storage.js",
  "/manifest.webmanifest",
  "/icon.svg",
  "/assets/gradio-ui-preview.svg",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) =>
      Promise.all(
        APP_SHELL.map((url) =>
          cache.add(new Request(url, { cache: "reload" })).catch(() => null)
        )
      )
    )
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
  if (url.origin !== self.location.origin) return;

  // Navigation requests: network-first so updates ship, fall back to cached shell.
  if (event.request.mode === "navigate") {
    event.respondWith(
      fetch(event.request)
        .then((response) => {
          const copy = response.clone();
          caches.open(CACHE_NAME).then((cache) => {
            const key = url.pathname.startsWith("/web") ? "/web/index.html" : "/index.html";
            cache.put(key, copy).catch(() => {});
          });
          return response;
        })
        .catch(() => {
          const key = url.pathname.startsWith("/web") ? "/web/index.html" : "/index.html";
          return caches.match(key).then((cached) => cached || caches.match("/index.html"));
        })
    );
    return;
  }

  // API endpoints should always try network; if offline, surface a useful JSON payload.
  if (url.pathname.startsWith("/api/")) {
    event.respondWith(
      fetch(event.request).catch(() =>
        new Response(
          JSON.stringify({ ok: false, error: "offline", path: url.pathname }),
          { status: 503, headers: { "Content-Type": "application/json; charset=utf-8" } }
        )
      )
    );
    return;
  }

  // Static assets: stale-while-revalidate.
  event.respondWith(
    caches.match(event.request).then((cached) => {
      const networkFetch = fetch(event.request)
        .then((response) => {
          if (response && response.ok) {
            const copy = response.clone();
            caches.open(CACHE_NAME).then((cache) => cache.put(event.request, copy)).catch(() => {});
          }
          return response;
        })
        .catch(() => cached);
      return cached || networkFetch;
    })
  );
});
