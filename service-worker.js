const CACHE_NAME = "audiobook-web-v7";
const APP_SHELL = [
  "/",
  "/index.html",
  "/website/index.html",
  "/web/index.html",
  "/web/api-client.js",
  "/web/audiobook-maker.js",
  "/web/chunker.js",
  "/web/processor.js",
  "/web/storage.js",
  "/manifest.webmanifest",
  "/icon.svg",
  "/assets/gradio-ui-preview.svg",
  "/api/launch",
  "/api/voices"
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(APP_SHELL).catch(() => undefined))
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key)))
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
          caches.open(CACHE_NAME).then((cache) => cache.put(event.request, copy)).catch(() => {});
          return response;
        })
        .catch(() => caches.match(event.request).then((c) => c || caches.match("/web/index.html")))
    );
    return;
  }

  if (url.pathname.startsWith("/api/")) {
    // Never cache the TTS endpoint (it is large, dynamic, and costs money).
    if (url.pathname === "/api/tts") {
      event.respondWith(fetch(event.request));
      return;
    }
    if (url.pathname === "/api/voices" || url.pathname === "/api/launch") {
      event.respondWith(
        fetch(event.request)
          .then((response) => {
            if (response && response.ok) {
              const copy = response.clone();
              caches.open(CACHE_NAME).then((cache) => cache.put(event.request, copy)).catch(() => {});
            }
            return response;
          })
          .catch(() => caches.match(event.request))
      );
      return;
    }
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
    caches.match(event.request).then((cached) => {
      if (cached) return cached;
      return fetch(event.request).then((response) => {
        if (response && response.ok) {
          const copy = response.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(event.request, copy)).catch(() => {});
        }
        return response;
      });
    })
  );
});
