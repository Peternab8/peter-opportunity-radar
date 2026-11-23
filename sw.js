self.addEventListener('install', (e) => self.skipWaiting());
self.addEventListener('activate', (e) => e.waitUntil(self.clients.claim()));

self.addEventListener('fetch', (event) => {
  if (event.request.url.includes('live_feed.json')) {
    event.respondWith(
      fetch(event.request, { cache: 'no-store' }).catch(() => caches.match(event.request))
    );
  }
});

self.addEventListener('push', (event) => {
  const data = event.data ? event.data.json() : {
    title: 'فرصة جديدة مطابقة — رادار بيتر',
    body: 'اضغط لفتح بطاقة الفرصة',
    deep_link: './index.html'
  };
  event.waitUntil(
    self.registration.showNotification(data.title, {
      body: data.body,
      tag: data.job_id || 'radar-alert',
      data: { url: data.deep_link || './index.html' },
      actions: [
        { action: 'open', title: 'افتح الإعلان' },
        { action: 'save', title: 'احفظ' }
      ]
    })
  );
});

self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  const targetUrl = (event.notification.data && event.notification.data.url) || './index.html';
  event.waitUntil(clients.openWindow(targetUrl));
});
