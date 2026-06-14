/* Remndrs service worker — web push delivery + click-to-open.
 * Served from /sw.js (root scope) so it controls the whole app. */

self.addEventListener('push', event => {
  let data = {};
  try { data = event.data ? event.data.json() : {}; } catch (e) { /* non-JSON */ }
  const title = data.title || 'Remndrs';
  event.waitUntil(
    self.registration.showNotification(title, {
      body: data.body || '',
      icon: '/static/favicon.svg',
      badge: '/static/favicon.svg',
      tag: data.tag || 'remndrs',
      data: { url: data.url || '/' },
    })
  );
});

self.addEventListener('notificationclick', event => {
  event.notification.close();
  const target = (event.notification.data && event.notification.data.url) || '/';
  event.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true }).then(wins => {
      for (const w of wins) {
        // Focus an already-open Remndrs tab rather than spawning another.
        if ('focus' in w) { w.navigate ? w.navigate(target) : null; return w.focus(); }
      }
      if (clients.openWindow) return clients.openWindow(target);
    })
  );
});
