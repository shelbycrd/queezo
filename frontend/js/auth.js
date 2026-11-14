import {api} from './api.js';
import {authenticatedUser, onUnauthorized, setAuthenticatedUser} from './auth-state.js';
import {app, mount, notice} from './ui.js';

let sequence = 0;
let changed = () => {};
let loginMessage = '';
let channel;

function adopt(user) {
  const previous = authenticatedUser();
  setAuthenticatedUser(user);
  document.body.classList.toggle('signed-in', Boolean(user));
  document.querySelector('#main-navigation').hidden = !user;
  document.querySelector('#account-controls').hidden = !user;
  document.querySelector('#account-email').textContent = user?.email || '';
  if (previous?.id !== user?.id) changed(previous, user);
}

export function expireSession(message = 'Your session has expired. Please log in again.') {
  sequence++;
  loginMessage = message;
  adopt(null);
  location.replace('#login');
}

export async function restoreSession() {
  const ticket = ++sequence;
  try {
    const user = await api('/auth/me', {ignoreUnauthorized:true});
    if (ticket !== sequence) return authenticatedUser();
    adopt(user);
    return user;
  } catch (error) {
    if (ticket !== sequence) return authenticatedUser();
    if (error.status === 401) { adopt(null); return null; }
    throw error;
  }
}

export function initAuth(onChanged) {
  changed = onChanged;
  onUnauthorized(() => expireSession());
  if ('BroadcastChannel' in window) {
    channel = new BroadcastChannel('queezo.account');
    channel.onmessage = event => {
      if (!['signed-out','changed'].includes(event.data?.type)) return;
      // Hide the previous account's page before checking a changed shared cookie.
      expireSession(event.data.type === 'signed-out' ? 'You have been logged out.' : 'Your account session changed.');
      if (event.data.type === 'changed') void restoreSession().then(user => {
        if (user) location.replace('#dashboard');
      }).catch(() => {});
    };
  }
  document.querySelector('#logout').addEventListener('click', async event => {
    const button = event.currentTarget;
    if (button.disabled) return;
    button.disabled = true;
    try {
      await api('/auth/logout', {method:'POST', ignoreUnauthorized:true});
      expireSession('You have been logged out.');
      channel?.postMessage({type:'signed-out'});
    } catch (error) {
      if (error.status === 401) expireSession();
      else notice('Logout could not be completed. Check your connection and try again.');
    } finally { button.disabled = false; }
  });
  const check = async () => {
    if (!authenticatedUser() || document.hidden) return;
    try {
      const previousId = authenticatedUser().id;
      const user = await restoreSession();
      if (!user) expireSession();
      else if (user.id !== previousId) location.replace('#dashboard');
    } catch { /* A transient network failure does not claim to revoke a session. */ }
  };
  window.addEventListener('focus', check);
  document.addEventListener('visibilitychange', check);
  setInterval(check, 60000);
}

export function loginPage(route) {
  if (!mount(`<section class="panel login-panel"><p class="eyebrow">Welcome to Queezo</p><h1>Log in to your study space.</h1><p class="muted">Use the account provided to you.</p>
    <form id="login-form"><label for="login-email">Email</label><input id="login-email" name="email" type="email" autocomplete="username" maxlength="254" required>
    <label for="login-password">Password</label><input id="login-password" name="password" type="password" autocomplete="current-password" required>
    <p id="login-error" class="inline-error" role="alert" hidden></p><p id="login-message" class="hint" role="status"></p><button type="submit">Log in</button></form></section>`, route)) return;
  const form = app.querySelector('#login-form');
  const error = form.querySelector('#login-error');
  form.querySelector('#login-message').textContent = loginMessage;
  loginMessage = '';
  form.addEventListener('submit', async event => {
    event.preventDefault();
    const button = form.querySelector('button');
    if (button.disabled || !form.reportValidity()) return;
    const ticket = ++sequence;
    error.hidden = true;
    button.disabled = true;
    button.textContent = 'Logging in…';
    try {
      const user = await api('/auth/login', {method:'POST', body:{email:form.elements.email.value, password:form.elements.password.value}, ignoreUnauthorized:true});
      if (ticket !== sequence || !form.isConnected || location.hash !== route) return;
      adopt(user);
      channel?.postMessage({type:'changed'});
      location.replace('#dashboard');
    } catch (failure) {
      if (ticket !== sequence || !form.isConnected || location.hash !== route) return;
      error.textContent = failure.message;
      error.hidden = false;
    } finally {
      form.elements.password.value = '';
      button.disabled = false;
      button.textContent = 'Log in';
    }
  });
}
