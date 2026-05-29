/* sw.js — service worker dla PWA (offline-first dla powłoki aplikacji).
   Zasada: dane prywatne i pogodowe (/api/, /uploads/, /login) zawsze z sieci;
   powłoka (HTML, CSS, JS, ikona) cache'owana, by aplikacja działała offline. */

const CACHE = 'planer-wedkarski-v1';
const SHELL = [
    '/',
    '/static/style.css',
    '/static/script.js',
    '/static/icon.svg',
    '/manifest.webmanifest',
];

self.addEventListener('install', (e) => {
    e.waitUntil(
        caches.open(CACHE)
            .then((c) => c.addAll(SHELL))
            .then(() => self.skipWaiting())
            .catch(() => {})
    );
});

self.addEventListener('activate', (e) => {
    e.waitUntil(
        caches.keys()
            .then((keys) => Promise.all(
                keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))
            ))
            .then(() => self.clients.claim())
    );
});

self.addEventListener('fetch', (e) => {
    const req = e.request;
    if (req.method !== 'GET') return;                  // nigdy nie cache'ujemy POST/PUT/DELETE

    const url = new URL(req.url);
    if (url.origin !== self.location.origin) return;   // pomijamy cross-origin (Leaflet, Overpass, Wiki)

    // Dynamiczne / prywatne — zawsze z sieci
    if (url.pathname.startsWith('/api/') ||
        url.pathname.startsWith('/uploads/') ||
        url.pathname === '/login' ||
        url.pathname === '/logout' ||
        url.pathname === '/sw.js') {
        return;
    }

    // Nawigacje: network-first z fallbackiem do zcache'owanej powłoki
    if (req.mode === 'navigate') {
        e.respondWith(
            fetch(req)
                .then((res) => {
                    const copy = res.clone();
                    caches.open(CACHE).then((c) => c.put('/', copy)).catch(() => {});
                    return res;
                })
                .catch(() => caches.match(req).then((r) => r || caches.match('/')))
        );
        return;
    }

    // Statyczne zasoby: stale-while-revalidate
    e.respondWith(
        caches.match(req).then((cached) => {
            const network = fetch(req)
                .then((res) => {
                    if (res && res.status === 200) {
                        const copy = res.clone();
                        caches.open(CACHE).then((c) => c.put(req, copy)).catch(() => {});
                    }
                    return res;
                })
                .catch(() => cached);
            return cached || network;
        })
    );
});
