const CACHE_NAME = 'luma-journal-v1';
const APP_SHELL = [
  '/',
  '/manifest.json',
  '/icons/favicon-32.png',
  '/icons/apple-touch-icon.png',
  '/icons/luma-journal-192.png',
  '/icons/luma-journal-512.png',
];

async function precacheAppShell() {
  const cache = await caches.open(CACHE_NAME);
  await cache.addAll(APP_SHELL);

  const indexHtml = await (await cache.match('/')).text();
  const assets = Array.from(
    indexHtml.matchAll(/(?:src|href)="([^"]+)"/g),
    (match) => match[1],
  ).filter((path) => path.startsWith('/assets/') && /\.(?:js|css)$/.test(path));
  await cache.addAll(assets);
}

self.addEventListener('install', (event) => {
  event.waitUntil(Promise.all([precacheAppShell(), self.skipWaiting()]));
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    Promise.all([
      caches.keys().then((keys) => Promise.all(
        keys
          .filter((key) => key.startsWith('luma-journal-') && key !== CACHE_NAME)
          .map((key) => caches.delete(key)),
      )),
      self.clients.claim(),
    ]),
  );
});

self.addEventListener('fetch', (event) => {
  const { request } = event;
  const url = new URL(request.url);

  if (
    request.method !== 'GET'
    || url.origin !== self.location.origin
    || url.pathname.startsWith('/api/')
  ) {
    return;
  }

  if (request.mode === 'navigate') {
    event.respondWith((async () => {
      const cache = await caches.open(CACHE_NAME);
      try {
        const response = await fetch(request);
        if (response.ok) await cache.put(request, response.clone());
        return response;
      } catch {
        return (await cache.match(request)) || (await cache.match('/'));
      }
    })());
    return;
  }

  event.respondWith((async () => {
    const cached = await caches.match(request);
    if (cached) return cached;

    const response = await fetch(request);
    if (response.ok) {
      const cache = await caches.open(CACHE_NAME);
      await cache.put(request, response.clone());
    }
    return response;
  })());
});
