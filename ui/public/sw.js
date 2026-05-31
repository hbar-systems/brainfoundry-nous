// Minimal service worker — static-asset cache + network-first navigation.
// Bumps CACHE_NAME on each release to invalidate the previous cache.
// Bump this string when shipping a new SW or asset set.
const CACHE_NAME = 'bf-static-v3';

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

  // Page navigations (HTML): go to network with cache:'no-store' so a refresh
  // after a deploy ALWAYS gets the fresh page — and therefore the fresh,
  // content-hashed JS chunk references. This is the fix for "I updated but the
  // UI looks the same": stale HTML would point at old chunks. Cache only as an
  // offline fallback. (Without no-store the browser HTTP cache could hand the
  // SW a stale page even though it's "network-first".)
  if (req.mode === 'navigate') {
    event.respondWith(
      fetch(req, { cache: 'no-store' })
        .then((resp) => {
          if (resp && resp.ok && resp.type === 'basic') {
            const copy = resp.clone();
            caches.open(CACHE_NAME).then((c) => c.put('/', copy)).catch(() => {});
          }
          return resp;
        })
        .catch(() => caches.match(req).then((m) => m || caches.match('/')))
    );
    return;
  }

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
