/*!
 * Treatment Navigator - Service Worker
 * Provides offline support and caching for healthcare applications
 * Prioritizes critical features and emergency information
 */

const CACHE_NAME = 'treatment-navigator-v1.0.0';
const OFFLINE_URL = '/offline.html';

// Critical resources that should always be cached
const CRITICAL_RESOURCES = [
    '/',
    '/offline.html',
    '/static/css/common.css',
    '/static/css/vision.css',
    '/static/js/common.js',
    '/static/fonts/nunito-regular.woff2',
    '/static/fonts/nunito-bold.woff2',
    '/crisis-resources',
    '/help'
];

// Crisis resources that must be available offline
const CRISIS_RESOURCES = [
    '/crisis-resources',
    '/emergency-contacts',
    '/suicide-prevention',
    '/mental-health-crisis'
];

// API endpoints to cache for offline use
const CACHEABLE_APIS = [
    '/api/health',
    '/api/crisis-resources',
    '/api/emergency-contacts'
];

// Assets that can be cached when accessed
const CACHEABLE_PATTERNS = [
    /\.(?:png|jpg|jpeg|svg|gif|webp)$/,
    /\.(?:css|js)$/,
    /\.(?:woff|woff2|ttf|eot)$/
];

// Install event - cache critical resources
self.addEventListener('install', (event) => {
    console.log('[ServiceWorker] Installing...');
    
    event.waitUntil(
        (async () => {
            try {
                const cache = await caches.open(CACHE_NAME);
                
                // Cache critical resources with error handling
                const cachePromises = CRITICAL_RESOURCES.map(async (url) => {
                    try {
                        await cache.add(url);
                        console.log(`[ServiceWorker] Cached: ${url}`);
                    } catch (error) {
                        console.warn(`[ServiceWorker] Failed to cache: ${url}`, error);
                    }
                });
                
                await Promise.allSettled(cachePromises);
                
                // Pre-cache crisis resources
                const crisisPromises = CRISIS_RESOURCES.map(async (url) => {
                    try {
                        const response = await fetch(url);
                        if (response.ok) {
                            await cache.put(url, response);
                            console.log(`[ServiceWorker] Crisis resource cached: ${url}`);
                        }
                    } catch (error) {
                        console.warn(`[ServiceWorker] Failed to cache crisis resource: ${url}`, error);
                    }
                });
                
                await Promise.allSettled(crisisPromises);
                
                console.log('[ServiceWorker] Installation complete');
            } catch (error) {
                console.error('[ServiceWorker] Installation failed:', error);
            }
        })()
    );
    
    // Force activation of new service worker
    self.skipWaiting();
});

// Activate event - clean up old caches
self.addEventListener('activate', (event) => {
    console.log('[ServiceWorker] Activating...');
    
    event.waitUntil(
        (async () => {
            try {
                // Clean up old caches
                const cacheNames = await caches.keys();
                const deletionPromises = cacheNames
                    .filter(cacheName => cacheName !== CACHE_NAME)
                    .map(cacheName => caches.delete(cacheName));
                
                await Promise.all(deletionPromises);
                
                // Claim control of all clients
                await self.clients.claim();
                
                console.log('[ServiceWorker] Activation complete');
            } catch (error) {
                console.error('[ServiceWorker] Activation failed:', error);
            }
        })()
    );
});

// Fetch event - handle network requests with caching strategies
self.addEventListener('fetch', (event) => {
    const { request } = event;
    const url = new URL(request.url);
    
    // Skip non-GET requests and chrome-extension URLs
    if (request.method !== 'GET' || url.protocol === 'chrome-extension:') {
        return;
    }
    
    // Handle different types of requests with appropriate strategies
    if (isCrisisResource(url)) {
        // Crisis resources: Cache first, then network
        event.respondWith(handleCrisisResource(request));
    } else if (isApiRequest(url)) {
        // API requests: Network first, then cache
        event.respondWith(handleApiRequest(request));
    } else if (isStaticAsset(url)) {
        // Static assets: Cache first, then network
        event.respondWith(handleStaticAsset(request));
    } else if (isNavigationRequest(request)) {
        // Navigation requests: Network first, then cache, then offline page
        event.respondWith(handleNavigationRequest(request));
    } else {
        // Other requests: Network first
        event.respondWith(handleGenericRequest(request));
    }
});

// Handle crisis resources - prioritize offline availability
async function handleCrisisResource(request) {
    try {
        const cachedResponse = await caches.match(request);
        if (cachedResponse) {
            // Return cached version immediately for crisis resources
            return cachedResponse;
        }
        
        // Try network if not in cache
        const networkResponse = await fetch(request);
        if (networkResponse.ok) {
            const cache = await caches.open(CACHE_NAME);
            cache.put(request, networkResponse.clone());
        }
        return networkResponse;
        
    } catch (error) {
        console.error('[ServiceWorker] Crisis resource fetch failed:', error);
        
        // Return a fallback crisis page if available
        const fallback = await caches.match('/crisis-resources');
        if (fallback) {
            return fallback;
        }
        
        // Last resort - return offline page
        return caches.match(OFFLINE_URL);
    }
}

// Handle API requests - fresh data preferred, cached as fallback
async function handleApiRequest(request) {
    try {
        const networkResponse = await fetch(request, { timeout: 5000 });
        
        if (networkResponse.ok) {
            // Cache successful API responses
            const cache = await caches.open(CACHE_NAME);
            cache.put(request, networkResponse.clone());
        }
        
        return networkResponse;
        
    } catch (error) {
        console.warn('[ServiceWorker] API request failed, trying cache:', error);
        
        const cachedResponse = await caches.match(request);
        if (cachedResponse) {
            // Add a custom header to indicate this is a cached response
            const response = cachedResponse.clone();
            response.headers.set('X-From-Cache', 'true');
            return response;
        }
        
        // Return a generic error response for API failures
        return new Response(
            JSON.stringify({
                error: 'Service temporarily unavailable',
                offline: true,
                timestamp: new Date().toISOString()
            }),
            {
                status: 503,
                statusText: 'Service Unavailable',
                headers: {
                    'Content-Type': 'application/json',
                    'X-Offline': 'true'
                }
            }
        );
    }
}

// Handle static assets - cache first for performance
async function handleStaticAsset(request) {
    try {
        const cachedResponse = await caches.match(request);
        if (cachedResponse) {
            return cachedResponse;
        }
        
        const networkResponse = await fetch(request);
        if (networkResponse.ok) {
            const cache = await caches.open(CACHE_NAME);
            cache.put(request, networkResponse.clone());
        }
        
        return networkResponse;
        
    } catch (error) {
        console.warn('[ServiceWorker] Static asset fetch failed:', error);
        
        // Try to return cached version
        const cachedResponse = await caches.match(request);
        if (cachedResponse) {
            return cachedResponse;
        }
        
        // Return a 404 for missing assets
        return new Response('Asset not found', { 
            status: 404, 
            statusText: 'Not Found' 
        });
    }
}

// Handle navigation requests - fresh content preferred
async function handleNavigationRequest(request) {
    try {
        const networkResponse = await fetch(request, { timeout: 8000 });
        
        if (networkResponse.ok) {
            // Cache successful page responses
            const cache = await caches.open(CACHE_NAME);
            cache.put(request, networkResponse.clone());
        }
        
        return networkResponse;
        
    } catch (error) {
        console.warn('[ServiceWorker] Navigation request failed:', error);
        
        // Try cached version
        const cachedResponse = await caches.match(request);
        if (cachedResponse) {
            return cachedResponse;
        }
        
        // Return offline page as last resort
        return caches.match(OFFLINE_URL);
    }
}

// Handle generic requests
async function handleGenericRequest(request) {
    try {
        return await fetch(request);
    } catch (error) {
        console.warn('[ServiceWorker] Generic request failed:', error);
        return new Response('Request failed', { 
            status: 500, 
            statusText: 'Internal Server Error' 
        });
    }
}

// Utility functions
function isCrisisResource(url) {
    return CRISIS_RESOURCES.some(pattern => 
        url.pathname.includes(pattern) || url.pathname === pattern
    );
}

function isApiRequest(url) {
    return url.pathname.startsWith('/api/') || 
           CACHEABLE_APIS.some(pattern => url.pathname === pattern);
}

function isStaticAsset(url) {
    return CACHEABLE_PATTERNS.some(pattern => pattern.test(url.pathname)) ||
           url.pathname.startsWith('/static/');
}

function isNavigationRequest(request) {
    return request.mode === 'navigate' || 
           (request.method === 'GET' && 
            request.headers.get('accept') && 
            request.headers.get('accept').includes('text/html'));
}

// Background sync for offline form submissions
self.addEventListener('sync', (event) => {
    console.log('[ServiceWorker] Background sync triggered:', event.tag);
    
    if (event.tag === 'background-sync-form') {
        event.waitUntil(handleBackgroundSync());
    }
});

async function handleBackgroundSync() {
    try {
        // Get pending form submissions from IndexedDB
        const db = await openDB();
        const tx = db.transaction(['pendingForms'], 'readonly');
        const store = tx.objectStore('pendingForms');
        const pendingForms = await store.getAll();
        
        for (const form of pendingForms) {
            try {
                const response = await fetch(form.url, {
                    method: form.method,
                    headers: form.headers,
                    body: form.body
                });
                
                if (response.ok) {
                    // Remove successfully submitted form
                    const deleteTx = db.transaction(['pendingForms'], 'readwrite');
                    const deleteStore = deleteTx.objectStore('pendingForms');
                    await deleteStore.delete(form.id);
                    
                    console.log('[ServiceWorker] Form submitted successfully:', form.id);
                }
            } catch (error) {
                console.warn('[ServiceWorker] Form submission failed:', error);
            }
        }
    } catch (error) {
        console.error('[ServiceWorker] Background sync failed:', error);
    }
}

// Push notification handling for crisis alerts
self.addEventListener('push', (event) => {
    if (!event.data) return;
    
    try {
        const data = event.data.json();
        
        const options = {
            body: data.body || 'Treatment Navigator notification',
            icon: '/static/icons/icon-192x192.png',
            badge: '/static/icons/badge-72x72.png',
            tag: data.tag || 'default',
            requireInteraction: data.priority === 'high',
            actions: data.actions || [],
            data: data.data || {}
        };
        
        // Special handling for crisis notifications
        if (data.type === 'crisis') {
            options.requireInteraction = true;
            options.sound = '/static/sounds/crisis-alert.mp3';
            options.vibrate = [200, 100, 200];
            options.badge = '/static/icons/crisis-badge.png';
        }
        
        event.waitUntil(
            self.registration.showNotification(
                data.title || 'Treatment Navigator',
                options
            )
        );
    } catch (error) {
        console.error('[ServiceWorker] Push notification error:', error);
    }
});

// Notification click handling
self.addEventListener('notificationclick', (event) => {
    event.notification.close();
    
    const { action, data } = event;
    let url = '/';
    
    if (data && data.url) {
        url = data.url;
    } else if (action === 'crisis') {
        url = '/crisis-resources';
    } else if (action === 'help') {
        url = '/help';
    }
    
    event.waitUntil(
        clients.matchAll({ type: 'window' }).then((clientList) => {
            // Try to focus existing window
            for (const client of clientList) {
                if (client.url === url && 'focus' in client) {
                    return client.focus();
                }
            }
            
            // Open new window if no existing window found
            if (clients.openWindow) {
                return clients.openWindow(url);
            }
        })
    );
});

// Message handling for communication with main thread
self.addEventListener('message', (event) => {
    const { type, data } = event.data;
    
    switch (type) {
        case 'SKIP_WAITING':
            self.skipWaiting();
            break;
            
        case 'GET_VERSION':
            event.ports[0].postMessage({ version: CACHE_NAME });
            break;
            
        case 'CLEAR_CACHE':
            event.waitUntil(clearCache(data.cacheName));
            break;
            
        case 'CACHE_URLS':
            event.waitUntil(cacheUrls(data.urls));
            break;
            
        default:
            console.warn('[ServiceWorker] Unknown message type:', type);
    }
});

async function clearCache(cacheName) {
    try {
        const success = await caches.delete(cacheName || CACHE_NAME);
        console.log('[ServiceWorker] Cache cleared:', success);
        return success;
    } catch (error) {
        console.error('[ServiceWorker] Cache clear failed:', error);
        return false;
    }
}

async function cacheUrls(urls) {
    try {
        const cache = await caches.open(CACHE_NAME);
        await cache.addAll(urls);
        console.log('[ServiceWorker] URLs cached:', urls);
        return true;
    } catch (error) {
        console.error('[ServiceWorker] URL caching failed:', error);
        return false;
    }
}

// IndexedDB helper for offline form storage
async function openDB() {
    return new Promise((resolve, reject) => {
        const request = indexedDB.open('TreatmentNavigatorDB', 1);
        
        request.onerror = () => reject(request.error);
        request.onsuccess = () => resolve(request.result);
        
        request.onupgradeneeded = (event) => {
            const db = event.target.result;
            
            if (!db.objectStoreNames.contains('pendingForms')) {
                const store = db.createObjectStore('pendingForms', { keyPath: 'id' });
                store.createIndex('timestamp', 'timestamp', { unique: false });
            }
        };
    });
}

// Performance monitoring
self.addEventListener('fetch', (event) => {
    if (event.request.url.includes('/api/')) {
        const startTime = performance.now();
        
        event.respondWith(
            fetch(event.request).then(response => {
                const endTime = performance.now();
                const duration = endTime - startTime;
                
                // Log slow API requests
                if (duration > 2000) {
                    console.warn(`[ServiceWorker] Slow API request: ${event.request.url} (${duration}ms)`);
                }
                
                return response;
            })
        );
    }
});

console.log('[ServiceWorker] Service Worker loaded successfully'); 