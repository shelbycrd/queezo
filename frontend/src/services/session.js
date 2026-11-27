import {ref, shallowRef} from 'vue';
import {api} from '../../js/api.js';
import {authenticatedUser, onUnauthorized, setAuthenticatedUser} from '../../js/auth-state.js';
import {showNotice} from './notice.js';

export const account = shallowRef(null);
export const loginMessage = ref('');
export const loginMessageSuccess = ref(false);
let sequence = 0;

function adopt(user) {
  setAuthenticatedUser(user);
  account.value = authenticatedUser();
}

export function updateAccountProfile({display_name,avatar}) {
  if (!account.value) return;
  sequence++;
  adopt({...account.value,display_name,avatar});
}

export function initAuthentication(router) {
  const events = new AbortController();
  const channel = 'BroadcastChannel' in window ? new BroadcastChannel('queezo.account') : null;
  function expire(message = 'Your session has expired. Please log in again.', success = false) {
    sequence++;
    loginMessage.value = message;
    loginMessageSuccess.value = success;
    adopt(null);
    void router.replace('/login');
  }
  async function restore() {
    const ticket = ++sequence;
    try {
      const user = await api('/auth/me', {ignoreUnauthorized:true, signal:events.signal});
      if (ticket === sequence) adopt(user);
    } catch (error) {
      if (ticket !== sequence) return account.value;
      if (error.status !== 401) throw error;
      adopt(null);
    }
    return account.value;
  }
  async function authenticate(action, body, active) {
    const ticket = ++sequence;
    const target = router.currentRoute.value.query.returnTo;
    const user = await api('/auth/' + action, {method:'POST', body, ignoreUnauthorized:true});
    if (ticket !== sequence || !active()) return;
    adopt(user);
    channel?.postMessage({type:'changed'});
    await router.replace(typeof target === 'string' && /^\/shared\/[A-Za-z0-9_-]{32,64}$/.test(target) ? target : '/home');
  }
  async function changePassword(body) {
    // The server ends every session after a change, this one included.
    const result = await api('/auth/password',{method:'POST',body,ignoreUnauthorized:true});
    channel?.postMessage({type:'password-changed'});
    expire(result?.message || 'Password changed. Log in again with your new password.', true);
  }
  async function logout() {
    try {
      await api('/auth/logout', {method:'POST', ignoreUnauthorized:true});
      expire('You have been logged out.');
      channel?.postMessage({type:'signed-out'});
    } catch (error) {
      if (error.status === 401) expire();
      else showNotice('Logout could not be completed. Check your connection and try again.');
    }
  }
  async function check() {
    if (!account.value || document.hidden) return;
    try {
      const previous = account.value.id;
      const user = await restore();
      if (!user) expire();
      else if (user.id !== previous) await router.replace('/home');
    } catch { /* Keep the session during a transient network error. */ }
  }
  // A late 401 after an intentional sign-out must not replace that sign-out message.
  onUnauthorized(() => { if (account.value) expire(); });
  if (channel) channel.onmessage = ({data}) => {
    if (data?.type === 'refreshed') {
      if (account.value) void check();
      return;
    }
    if (!['signed-out','changed','password-changed'].includes(data?.type)) return;
    expire({'signed-out':'You have been logged out.', 'password-changed':'Your password was changed. Log in again with your new password.'}[data.type]
      || 'Your account session changed.');
    if (data.type === 'changed') void restore().then(user => {
      if (user) return router.replace('/home');
    }).catch(() => {});
  };
  for (const [target, type] of [[window,'focus'],[document,'visibilitychange']]) {
    target.addEventListener(type, check, {signal:events.signal});
  }
  const timer = setInterval(check, 60000);
  return {restore, authenticate, changePassword, logout, stop() {
    events.abort(); channel?.close(); clearInterval(timer); onUnauthorized(() => {});
  }};
}
