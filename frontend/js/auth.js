import {api} from './api.js';
import {authenticatedUser, onUnauthorized, setAuthenticatedUser} from './auth-state.js';
import {app, mount, notice} from './ui.js';
import {passwordStrength} from './password-strength.js';

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
  document.querySelector('#account-email').textContent = user?.display_name || user?.username || user?.email?.split('@')[0] || '';
  document.querySelector('#account-avatar').textContent = (user?.display_name || user?.email || 'Q')[0].toUpperCase();
  document.querySelector('#account-dropdown').open = false;
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
  if (!mount(`<section class="panel login-panel"><p class="eyebrow">Welcome to Queezo</p><h1>Log in to Queezo.</h1><p class="muted">New here? <a href="#signup">Create an account</a>.</p>
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

export function signupPage(route) {
  if (!mount(`<section class="panel signup-panel"><h1>Create your account</h1><p class="muted">Already have an account? <a href="#login">Log in</a>.</p><form id="signup-form"><div class="signup-fields"><div><label for="signup-name">Display name</label><input id="signup-name" name="display_name" autocomplete="nickname" maxlength="80" required></div><div><label for="signup-username">Username</label><input id="signup-username" name="username" autocomplete="username" minlength="3" maxlength="32" pattern="[A-Za-z0-9_]{3,32}" required><p class="hint">3–32 letters, numbers, or underscores. Must be unique.</p></div><div class="full-width"><label for="signup-email">Email</label><input id="signup-email" name="email" type="email" autocomplete="email" maxlength="254" required></div><div class="full-width"><label for="signup-password">Password</label><input id="signup-password" name="password" type="password" autocomplete="new-password" minlength="11" maxlength="1024" required aria-describedby="strength-label password-advice"><div class="strength-heading"><span id="strength-label">Estimated strength</span><strong id="strength-level">Not entered</strong></div><progress id="password-strength" max="100" value="0" aria-label="Estimated password strength"></progress><ul id="password-advice" class="hint"><li>Try 12 or more characters.</li></ul><p class="hint">Only the 11-character minimum is required. Strength advice is optional.</p></div><div class="full-width"><label for="signup-confirm">Confirm password</label><input id="signup-confirm" name="confirm_password" type="password" autocomplete="new-password" minlength="11" maxlength="1024" required></div></div><p id="signup-error" class="inline-error" role="alert" hidden></p><button type="submit">Sign up</button></form></section>`, route)) return;
  const form = app.querySelector('#signup-form');
  const error = form.querySelector('#signup-error');
  const meter = form.querySelector('#password-strength');
  const updateStrength = () => {
    const result = passwordStrength(form.elements.password.value, [form.elements.display_name.value,form.elements.username.value,form.elements.email.value]);
    meter.value = result.score; meter.dataset.level = result.level.toLowerCase();
    meter.setAttribute('aria-valuetext',result.level);
    form.querySelector('#strength-level').textContent = result.level;
    const list = form.querySelector('#password-advice'); list.replaceChildren();
    result.tips.forEach(tip => { const item = document.createElement('li'); item.textContent = tip; list.append(item); });
  };
  form.addEventListener('input', updateStrength);
  form.addEventListener('input', () => form.elements.confirm_password.setCustomValidity(form.elements.confirm_password.value && form.elements.password.value !== form.elements.confirm_password.value ? 'Passwords do not match.' : ''));
  form.addEventListener('submit', async event => {
    event.preventDefault();
    const button = form.querySelector('[type=submit]');
    if (button.disabled || !form.reportValidity()) return;
    if (form.elements.password.value !== form.elements.confirm_password.value) { error.textContent = 'Passwords do not match.'; error.hidden = false; return; }
    const ticket = ++sequence;
    button.disabled = true; button.textContent = 'Creating account…'; error.hidden = true;
    try {
      const payload = Object.fromEntries(new FormData(form));
      const user = await api('/auth/signup',{method:'POST',body:payload,ignoreUnauthorized:true});
      if (ticket !== sequence || !form.isConnected || location.hash !== route) return;
      adopt(user); channel?.postMessage({type:'changed'}); location.replace('#dashboard');
    } catch (failure) {
      if (ticket === sequence && form.isConnected) { error.textContent = failure.message; error.hidden = false; }
    } finally {
      form.elements.password.value = ''; form.elements.confirm_password.value = ''; updateStrength();
      button.disabled = false; button.textContent = 'Sign up';
    }
  });
}
