// The Burrow — service worker v8
// Network-first for same-origin shell pages; everything else bypasses SW.
const CACHE = 'burrow-v8';
const SHELL = ['/', '/manifest.json'];

self.addEventListener('install', e => {
  e.waitUntil(
    caches.open(CACHE)
      .then(c => c.addAll(SHELL))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', e => {
  const url = new URL(e.request.url);

  // Skip cross-origin requests entirely — let the browser handle them.
  // The SW's fetch() is governed by connect-src CSP, which CF Access
  // restricts to 'self'. Intercepting cross-origin requests causes
  // CSP violations and ERR_FAILED.
  if (url.origin !== self.location.origin) return;

  // API calls and non-GET requests always go straight to network
  if (url.pathname.startsWith('/api/')) return;
  if (e.request.method !== 'GET') return;

  e.respondWith(
    fetch(e.request)
      .then(res => {
        if (SHELL.includes(url.pathname)) {
          const clone = res.clone();
          caches.open(CACHE).then(c => c.put(e.request, clone));
        }
        return res;
      })
      .catch(() => caches.match(e.request))
  );
});
