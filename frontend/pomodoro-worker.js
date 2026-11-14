// Persistent notification support; this worker does not cache or intercept pages.
self.addEventListener('notificationclick', event => {
  event.notification.close();
  event.waitUntil((async () => {
    const url = new URL('/#pomodoro', self.location.origin).href;
    const tabs = await self.clients.matchAll({type:'window', includeUncontrolled:true});
    const existing = tabs.find(client => new URL(client.url).origin === self.location.origin);
    if (existing) {
      await existing.navigate(url);
      await existing.focus();
    } else await self.clients.openWindow(url);
  })());
});
