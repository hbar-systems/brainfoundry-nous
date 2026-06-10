// Minimal service worker — static-asset cache only.
// Bumps CACHE_NAME on each release to invalidate the previous cache.
// Bump this string when shipping a new SW or asset set.
const CACHE_NAME = 'bf-static-v4';

const STATIC_ASSETS = [
  '/',
  '/manifest.json',
  '/icon.svg',
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then((cache) => cache.addAll(STATIC_ASSETS))
      .then(() => self.skipWaiting())
      .catch(() => {})
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(
        keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k))
      ))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (event) => {
  const req = event.request;
  if (req.method !== 'GET') return;

  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;

  // Never intercept API calls — let chat, upload, settings hit the network
  // every time so the brain UI is always live.
  if (url.pathname.startsWith('/api/')) return;
  if (url.pathname.startsWith('/_next/data/')) return;

  // Page navigations (HTML): DO NOT intercept. On an origin behind HTTP Basic
  // Auth, a service-worker-driven fetch cannot resolve the 401 auth challenge in
  // Firefox — it fails with "ServiceWorker intercepted the request and
  // encountered an unexpected error" and the page never loads (the login dialog
  // never appears). Letting navigations go straight to the browser lets it
  // handle both the HTML and the Basic-Auth dialog natively, in every browser.
  //
  // The previous network-first interception existed to avoid stale HTML after a
  // deploy (stale HTML → stale content-hashed chunk refs). That is now the job
  // of Cache-Control on HTML responses, not the SW — never of an SW that breaks
  // auth-gated hosts. So: bypass navigations entirely.
  if (req.mode === 'navigate') return;

  // Other GETs — content-hashed static assets, safe to cache. Network-first
  // with cached fallback offline.
  event.respondWith(
    fetch(req)
      .then((resp) => {
        if (resp && resp.ok && resp.type === 'basic') {
          const copy = resp.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(req, copy)).catch(() => {});
        }
        return resp;
      })
      .catch(() => caches.match(req).then((m) => m || caches.match('/')))
  );
});
