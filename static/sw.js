// The Burrow — service worker v5
// Network-first for shell pages; API calls bypass SW entirely.
const CACHE = 'burrow-v5';
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
     .then(() => {
       // Tell all open tabs to reload so they pick up the new version
       return self.clients.matchAll({ type: 'window' }).then(clients => {
         clients.forEach(c => c.postMessage({ type: 'SW_UPDATED' }));
       });
     })
  );
});

self.addEventListener('fetch', e => {
  // API calls and non-GET requests always go straight to network
  if (e.request.url.includes('/api/')) return;
  if (e.request.method !== 'GET') return;

  e.respondWith(
    fetch(e.request)
      .then(res => {
        if (SHELL.includes(new URL(e.request.url).pathname)) {
          const clone = res.clone();
          caches.open(CACHE).then(c => c.put(e.request, clone));
        }
        return res;
      })
      .catch(() => caches.match(e.request))
  );
});
