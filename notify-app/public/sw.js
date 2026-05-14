const CACHE = 'notify-v3';

self.addEventListener('install', e => {
  self.skipWaiting();
});

self.addEventListener('activate', e => {
  self.clients.claim();
});

// Show notification when server sends a push
self.addEventListener('push', e => {
  const data = e.data ? e.data.json() : { title: 'Notify', body: 'You have a reminder!' };
  e.waitUntil(
    self.registration.showNotification(data.title || 'Notify', {
      body:               data.body,
      tag:                data.tag || 'notify',
      icon:               '/icon.png',
      badge:              '/icon.png',
      vibrate:            [200, 100, 200, 100, 200],
      requireInteraction: true,
      actions: [
        { action: 'open',    title: 'Open app' },
        { action: 'dismiss', title: 'Dismiss'  }
      ]
    })
  );
});

self.addEventListener('notificationclick', e => {
  e.notification.close();
  if (e.action !== 'dismiss') {
    e.waitUntil(clients.openWindow('/'));
  }
});
