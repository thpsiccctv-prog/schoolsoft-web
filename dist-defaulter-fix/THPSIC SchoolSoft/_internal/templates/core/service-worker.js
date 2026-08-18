const CACHE_NAME = 'schoolsoft-v3';
const STATIC_ASSETS = [
    '/static/core/styles.css',
    '/static/core/school_logo.png',
    '/static/core/pwa-icon-192.png',
    '/static/core/pwa-icon-512.png'
];

// Install Event
self.addEventListener('install', (event) => {
    event.waitUntil(
        caches.open(CACHE_NAME).then((cache) => {
            console.log('Opened cache');
            return cache.addAll(STATIC_ASSETS);
        })
    );
    self.skipWaiting();
});

// Activate Event
self.addEventListener('activate', (event) => {
    event.waitUntil(
        caches.keys().then((cacheNames) => {
            return Promise.all(
                cacheNames.map((cacheName) => {
                    if (cacheName !== CACHE_NAME) {
                        return caches.delete(cacheName);
                    }
                })
            );
        })
    );
    self.clients.claim();
});

// Fetch Event
self.addEventListener('fetch', (event) => {
    const url = new URL(event.request.url);

    // CSS / JS: Network first so updates always show; cache is only an offline fallback.
    if (url.pathname.endsWith('.css') || url.pathname.endsWith('.js')) {
        event.respondWith(
            fetch(event.request).then(fetchRes => {
                const copy = fetchRes.clone();
                caches.open(CACHE_NAME).then(cache => cache.put(event.request, copy));
                return fetchRes;
            }).catch(() => caches.match(event.request))
        );
        return;
    }

    // Other static assets (images, icons): Cache first, fallback to network
    if (url.pathname.startsWith('/static/')) {
        event.respondWith(
            caches.match(event.request).then((response) => {
                return response || fetch(event.request).then(fetchRes => {
                    return caches.open(CACHE_NAME).then(cache => {
                        cache.put(event.request, fetchRes.clone());
                        return fetchRes;
                    });
                });
            })
        );
        return;
    }

    // Default: Network first, fallback to cache (don't aggressively cache HTML)
    event.respondWith(
        fetch(event.request).catch(() => {
            return caches.match(event.request);
        })
    );
});
