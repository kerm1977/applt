// Define el nombre de la caché y los archivos a cachear durante la instalación.
// Versión de la caché para permitir actualizaciones. Cambia este número para forzar una nueva caché.
// Hemos incrementado la versión para asegurar que los usuarios obtengan la nueva funcionalidad de notificaciones.
const CACHE_NAME = 'la-tribu-pwa-cache-v1.0.3'; 

// Lista de archivos esenciales que se cachearán al instalar el Service Worker.
// Asegúrate de incluir todas las rutas estáticas que tu aplicación necesita para funcionar offline.
const urlsToCache = [
    '/', // La página de inicio (que es ver_caminatas.html)
    '/static/css/main.css', // Tu CSS personalizado
    'https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css', // Bootstrap CSS
    'https://cdnjs.cloudflare.com/ajax/libs/font-awesome/5.15.4/css/all.min.css', // Font Awesome CSS
    'https://cdn.jsdelivr.net/npm/@popperjs/core@2.11.7/dist/umd/popper.min.js', // Popper.js
    'https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.min.js', // Bootstrap JS
    '/static/js/ckeditor.js', // CKEditor si lo usas globalmente
    // Archivos HTML específicos que quieres que estén disponibles offline
    '/ver_player', // La ruta para ver_player.html
    // Imágenes por defecto (si existen y son necesarias offline)
    '/static/images/defaults/default_avatar.png',
    '/static/images/defaults/default_caminata.png',
    '/static/images/defaults/default_calendar.png',
    '/static/images/defaults/no_image.png',
    // Íconos de la PWA (desde tu manifest.json) - Asegúrate de que estas rutas sean correctas
    '/static/uploads/icons/icon-192x192.jpg',
    '/static/uploads/icons/icon-512x512.jpg'
    // Agrega aquí cualquier otra ruta que necesites para el funcionamiento offline,
    // como otras páginas HTML (ej. /login, /register, etc.), JS específicos, etc.
];

// Evento 'install': Se dispara cuando el Service Worker se instala por primera vez.
// Aquí abrimos una caché y agregamos todos los archivos esenciales.
self.addEventListener('install', (event) => {
    console.log('[Service Worker] Instalando Service Worker...');
    event.waitUntil(
        caches.open(CACHE_NAME)
            .then((cache) => {
                console.log('[Service Worker] Cacheando archivos esenciales:', urlsToCache);
                return cache.addAll(urlsToCache);
            })
            .catch((error) => {
                console.error('[Service Worker] Falló la caché de archivos esenciales:', error);
            })
    );
});

// Evento 'activate': Se dispara cuando el Service Worker se activa.
// Aquí limpiamos las cachés antiguas para asegurar que solo la versión actual esté activa.
self.addEventListener('activate', (event) => {
    console.log('[Service Worker] Activando Service Worker...');
    event.waitUntil(
        caches.keys().then((cacheNames) => {
            return Promise.all(
                cacheNames.map((cacheName) => {
                    if (cacheName !== CACHE_NAME) {
                        console.log('[Service Worker] Eliminando caché antigua:', cacheName);
                        return caches.delete(cacheName);
                    }
                })
            );
        })
    );
    // Asegura que el Service Worker tome el control de las páginas existentes inmediatamente.
    return self.clients.claim();
});

// Evento 'fetch': Se dispara cada vez que el navegador solicita un recurso.
// Aquí interceptamos la solicitud y decidimos si servir desde la caché o la red.
self.addEventListener('fetch', (event) => {
    // Solo intercepta solicitudes GET.
    if (event.request.method !== 'GET') {
        return;
    }

    event.respondWith(
        caches.match(event.request)
            .then((response) => {
                // Si el recurso está en la caché, lo servimos desde allí.
                if (response) {
                    console.log('[Service Worker] Sirviendo desde caché:', event.request.url);
                    return response;
                }

                // Si no está en la caché, intentamos obtenerlo de la red.
                console.log('[Service Worker] Intentando obtener de la red:', event.request.url);
                return fetch(event.request)
                    .then((networkResponse) => {
                        // Si la solicitud de red fue exitosa, clonamos la respuesta
                        // y la guardamos en la caché para futuras solicitudes.
                        if (networkResponse && networkResponse.status === 200 && networkResponse.type === 'basic') {
                            const responseToCache = networkResponse.clone();
                            caches.open(CACHE_NAME)
                                .then((cache) => {
                                    cache.put(event.request, responseToCache);
                                    console.log('[Service Worker] Cacheando nueva respuesta:', event.request.url);
                                });
                        }
                        return networkResponse;
                    })
                    .catch(() => {
                        // Si la red falla y el recurso no está en caché, puedes servir una página offline.
                        console.log('[Service Worker] Falló la red y no hay caché para:', event.request.url);
                        if (event.request.mode === 'navigate') {
                            return caches.match('/offline.html'); // Asegúrate de tener un 'offline.html' en tu caché
                        }
                    });
            })
    );
});

// Evento 'message': Permite la comunicación entre la página y el Service Worker.
// Útil para enviar mensajes o forzar actualizaciones.
self.addEventListener('message', (event) => {
    if (event.data && event.data.type === 'SKIP_WAITING') {
        self.skipWaiting(); // Fuerza la activación del nuevo Service Worker
    }
});

// --- NUEVO: Manejo de notificaciones Push ---

// Evento 'push': Se dispara cuando el Service Worker recibe una notificación push del servidor.
self.addEventListener('push', (event) => {
    console.log('[Service Worker] Notificación Push recibida:', event);

    // Parsear los datos de la notificación. Se espera un objeto JSON.
    // El servidor debe enviar un JSON con 'title', 'body', 'icon' y 'url'.
    const data = event.data ? event.data.json() : {};
    const title = data.title || 'Nueva Actualización de La Tribu';
    const body = data.body || '¡Hay algo nuevo para ti!';
    const icon = data.icon || '/static/uploads/icons/icon-192x192.jpg'; // Icono por defecto
    const url = data.url || '/'; // URL a abrir al hacer clic en la notificación

    const options = {
        body: body,
        icon: icon,
        badge: icon, // Insignia para Android, suele ser el mismo icono
        data: {
            url: url // Guarda la URL para usarla en el evento 'notificationclick'
        }
    };

    // Muestra la notificación al usuario
    event.waitUntil(
        self.registration.showNotification(title, options)
    );
});

// Evento 'notificationclick': Se dispara cuando el usuario hace clic en una notificación.
self.addEventListener('notificationclick', (event) => {
    console.log('[Service Worker] Notificación clicada:', event);

    event.notification.close(); // Cierra la notificación al hacer clic

    // Obtiene la URL guardada en los datos de la notificación
    const targetUrl = event.notification.data.url;

    // Abre la URL en una nueva ventana o pestaña, o enfoca una existente
    event.waitUntil(
        clients.matchAll({ type: 'window', includeUncontrolled: true })
            .then((clientList) => {
                for (const client of clientList) {
                    // Si la URL ya está abierta en alguna pestaña, la enfoca
                    if (client.url.includes(targetUrl) && 'focus' in client) {
                        return client.focus(); 
                    }
                }
                // Si la URL no está abierta, abre una nueva ventana
                if (clients.openWindow) {
                    return clients.openWindow(targetUrl);
                }
            })
    );
});
