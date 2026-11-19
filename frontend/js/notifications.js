import {authenticatedUser} from './auth-state.js';
import {escape} from './ui.js';


let notifications;
export function resetNotifications() {
  notifications?.close();
  if (notifications) notifications.innerHTML = '';
}
export function initNotifications() {
  notifications = document.createElement('dialog'); notifications.id = 'notifications-panel'; notifications.setAttribute('aria-label','Notifications');
  document.body.append(notifications);
  const notificationButton = document.querySelector('#open-notifications');
  notificationButton.setAttribute('aria-haspopup','dialog');
  notificationButton.setAttribute('aria-controls','notifications-panel');
  notificationButton.setAttribute('aria-expanded','false');
  notifications.addEventListener('close', () => notificationButton.setAttribute('aria-expanded','false'));
  document.addEventListener('click', event => {
    if (notifications.open && !notifications.contains(event.target) && !notificationButton.contains(event.target)) notifications.close();
  });
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape' && notifications.open) { notifications.close(); notificationButton.focus(); }
  });
  document.querySelector('#open-notifications').onclick = () => {
    if (!authenticatedUser()) return;
    if (notifications.open) { notifications.close(); return; }
    const banner = document.querySelector('#pomodoro-alert');
    const title = banner.querySelector('strong').textContent;
    notifications.innerHTML = `<div class="drawer-heading"><h2>Notifications</h2><button class="secondary small flat-button" aria-label="Close notifications">×</button></div>${title ? `<article><h3>${escape(title)}</h3><p>${escape(banner.querySelector('p').textContent)}</p><a href="#pomodoro">Open timer</a></article>` : '<div class="notifications-empty"><h3>You’re all caught up</h3><p>Timer updates will appear here.</p></div>'}`;
    notifications.querySelector('button').onclick = () => notifications.close();
    notifications.querySelector('a')?.addEventListener('click', () => notifications.close());
    notifications.show();
    notificationButton.setAttribute('aria-expanded','true');
  };
}
