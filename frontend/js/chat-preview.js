import {authenticatedUser} from './auth-state.js';
import {escape} from './ui.js';

import {recentChats, validChats} from './chat-data.js';

let drawer, notifications;
export function resetCommunicationPanels() {
  drawer?.close(); notifications?.close();
  if (drawer) drawer.innerHTML = '';
  if (notifications) notifications.innerHTML = '';
}
export function initCommunicationPanels() {
  drawer = document.createElement('dialog'); drawer.id = 'chat-drawer'; drawer.setAttribute('aria-label','Your chats');
  notifications = document.createElement('dialog'); notifications.id = 'notifications-panel'; notifications.setAttribute('aria-label','Notifications');
  document.body.append(drawer, notifications);
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
  let chats = [], selected = null, owner = null;
  const key = () => `queezo.chat-preview.${owner}`;
  function save() {
    try { sessionStorage.setItem(key(), JSON.stringify(chats)); } catch { /* Preview stays available in memory. */ }
  }
  function render() {
    const chat = chats.find(item => item.id === selected);
    drawer.innerHTML = `<div class="drawer-heading">${chat ? '<button id="chats-back" class="secondary small flat-button" aria-label="Back to your chats">‹</button>' : ''}<h2>${chat ? escape(chat.name) : 'Your chats'}</h2><button id="close-chat" class="secondary small flat-button" aria-label="Close chats">×</button></div><p class="chat-preview-note">Local preview · messages stay in this tab. No messages are sent.</p>${chat ? `<div class="chat-messages">${chat.messages.length ? chat.messages.map(message => `<div class="chat-message"><p>${escape(message.text)}</p><small>Saved locally · ${escape(new Date(message.at).toLocaleTimeString([], {hour:'2-digit',minute:'2-digit'}))}</small></div>`).join('') : '<p class="muted">Write a message to preview this conversation.</p>'}</div><form id="chat-compose"><label class="sr-only" for="chat-message">Message</label><input id="chat-message" name="message" maxlength="2000" required placeholder="Write a message…" autocomplete="off"><button type="submit">Send</button></form>` : `<button id="new-chat" class="secondary small">New chat</button><form id="new-chat-form" hidden><label for="chat-name">Chat name</label><input id="chat-name" name="name" maxlength="80" required autocomplete="off"><button type="submit">Create preview</button></form><div class="chat-list">${chats.length ? recentChats(chats).map(item => `<button class="chat-row" data-chat="${escape(item.id)}"><span class="chat-avatar">${escape(item.name[0].toUpperCase())}</span><span><strong>${escape(item.name)}</strong><small>${escape(item.messages.at(-1)?.text || 'New conversation')}</small></span></button>`).join('') : '<div class="chat-empty"><h3>No chats yet</h3><p>Your most recent conversations will appear first.</p></div>'}</div>`}`;
    drawer.querySelector('#close-chat').onclick = closeDrawer;
    if (chat) {
      drawer.querySelector('#chats-back').onclick = () => { selected = null; render(); };
      drawer.querySelector('#chat-compose').onsubmit = event => {
        event.preventDefault();
        if (authenticatedUser()?.id !== owner) return;
        const text = event.currentTarget.elements.message.value.trim();
        if (!text) return;
        const at = Date.now(); chat.messages.push({text, at}); chat.messages = chat.messages.slice(-500); chat.updatedAt = at; save(); render(); drawer.querySelector('#chat-message').focus();
        drawer.querySelector('.chat-messages').scrollTop = drawer.querySelector('.chat-messages').scrollHeight;
      };
    } else {
      drawer.querySelector('#new-chat').onclick = () => { drawer.querySelector('#new-chat-form').hidden = false; drawer.querySelector('#chat-name').focus(); };
      drawer.querySelector('#new-chat-form').onsubmit = event => {
        event.preventDefault();
        if (authenticatedUser()?.id !== owner || chats.length >= 100) return;
        const name = event.currentTarget.elements.name.value.trim(); if (!name) return;
        const chat = {id:crypto.randomUUID(), name, updatedAt:Date.now(), messages:[]}; chats.push(chat); selected = chat.id; save(); render();
      };
      drawer.querySelectorAll('[data-chat]').forEach(button => { button.onclick = () => { selected = button.dataset.chat; render(); }; });
    }
  }
  function closeDrawer() {
    drawer.classList.add('closing');
    setTimeout(() => { drawer.close(); drawer.classList.remove('closing'); }, matchMedia('(prefers-reduced-motion: reduce)').matches ? 0 : 200);
  }
  drawer.addEventListener('cancel', event => { event.preventDefault(); closeDrawer(); });
  document.querySelector('#open-chats').onclick = () => {
    notifications.close();
    owner = authenticatedUser()?.id; if (!owner) return;
    try { chats = validChats(JSON.parse(sessionStorage.getItem(key()))); } catch { chats = []; }
    selected = null; render(); drawer.showModal();
  };
  document.querySelector('#open-notifications').onclick = () => {
    if (!authenticatedUser()) return;
    if (notifications.open) { notifications.close(); return; }
    const banner = document.querySelector('#pomodoro-alert');
    const title = banner.querySelector('strong').textContent;
    notifications.innerHTML = `<div class="drawer-heading"><h2>Notifications</h2><button class="secondary small flat-button" aria-label="Close notifications">×</button></div>${title ? `<article><h3>${escape(title)}</h3><p>${escape(banner.querySelector('p').textContent)}</p><a href="#pomodoro">Open timer</a></article>` : '<div class="chat-empty"><h3>You’re all caught up</h3><p>Timer updates will appear here.</p></div>'}`;
    notifications.querySelector('button').onclick = () => notifications.close();
    notifications.querySelector('a')?.addEventListener('click', () => notifications.close());
    notifications.show();
    notificationButton.setAttribute('aria-expanded','true');
  };
}
