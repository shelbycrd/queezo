import {ref, shallowRef, triggerRef} from 'vue';
import {api} from '../../js/api.js';
import {navigate} from './navigation.js';
import {advanceTimer, createState, pauseTimer, remainingMs, restoreState} from '../../js/pomodoro-core.js';

const STORAGE_PREFIX = 'queezo.pomodoro.v1.user.';
let storageKey = null;
let accountGeneration = 0;
const liveNotifications = new Set();
let state = createState();
let initialized = false;
export const storageAvailable = ref(true);
export const timerState = shallowRef(state);
export const timerText = ref('25:00');
export const timeRemaining = ref(state.intervalMs);
export const latestAlert = shallowRef(null);
export const timerAlert = ref(false);
export function dismissTimerAlert() { timerAlert.value = false; }
let serial = Promise.resolve();

function load() {
  if (!storageKey) return createState();
  try { return restoreState(JSON.parse(localStorage.getItem(storageKey))); }
  catch { return state; }
}

function save() {
  if (!storageKey) return;
  try { localStorage.setItem(storageKey, JSON.stringify(state)); storageAvailable.value = true; }
  catch { storageAvailable.value = false; }
}

function clockText(milliseconds) {
  const seconds = Math.ceil(milliseconds / 1000);
  return `${String(Math.floor(seconds / 60)).padStart(2,'0')}:${String(seconds % 60).padStart(2,'0')}`;
}

export function permissionStatus() {
  if (!('Notification' in window) || !window.isSecureContext) return 'unavailable';
  return Notification.permission;
}

async function notify(event, generation) {
  if (!storageKey || generation !== accountGeneration) return;
  latestAlert.value = event;
  timerAlert.value = true;
  if (permissionStatus() !== 'granted') return;
  try {
    const registration = 'serviceWorker' in navigator ? await navigator.serviceWorker.getRegistration() : null;
    if (!storageKey || generation !== accountGeneration) return;
    const options = {body:event.message, tag:`${storageKey}:${event.id}`, data:{url:'/#pomodoro'}};
    if (registration?.active) {
      await registration.showNotification(`Queezo · ${event.title}`, options);
      // Logout may occur while the browser is creating its persistent toast.
      // Its first cleanup can run before that toast exists, so close it again
      // after creation if it no longer belongs to the active account session.
      if (!storageKey || generation !== accountGeneration) {
        const notifications = await registration.getNotifications({tag:options.tag});
        notifications.forEach(notification => notification.close());
      }
    }
    else {
      const notification = new Notification(`Queezo · ${event.title}`, options);
      liveNotifications.add(notification);
      notification.onclose = () => liveNotifications.delete(notification);
      notification.onclick = () => {
        if (generation === accountGeneration && storageKey) { window.focus(); void navigate('/pomodoro'); }
        notification.close();
      };
    }
  } catch { /* The in-app alert is always available if system alerts fail. */ }
}

export function transact(action = () => {}, {skipOnCompletion = false} = {}) {
  const generation = accountGeneration;
  const key = storageKey;
  const operation = async () => {
    const update = () => {
      if (!key || storageKey !== key || generation !== accountGeneration) return;
      if (storageAvailable.value) state = load();
      const previousPomodoros = state.totalPomodoros;
      const event = advanceTimer(state);
      let failure;
      try { if (!event || !skipOnCompletion) action(state); } catch (error) { failure = error; }
      // Commit a completed interval even if the following user action is invalid.
      save(); updateClock();
      if (event && state.totalPomodoros > previousPomodoros && generation === accountGeneration && storageKey === key) {
        // A completed study interval marks this account's day, never a break.
        // The server records its own date and treats repeats as idempotent.
        void api('/activity/pomodoro', {method:'POST'}).catch(() => {});
      }
      if (event) void notify(event, generation);
      if (failure) throw failure;
    };
    if (navigator.locks) await navigator.locks.request(`queezo-pomodoro:${key}`, update);
    else update();
  };
  const result = serial.then(operation);
  serial = result.catch(() => {});
  return result;
}

function updateClock() {
  if (timerState.value === state) triggerRef(timerState);
  else timerState.value = state;
  timeRemaining.value = remainingMs(state);
  timerText.value = clockText(timeRemaining.value);
}

function tick() {
  if (!storageKey) return;
  if (state.running && state.deadline <= Date.now()) void transact();
  else updateClock();
}

export function startPomodoroClock() {
  if (initialized) return () => {};
  initialized = true;
  const events = new AbortController();
  const {signal} = events;
  window.addEventListener('storage', event => {
    if (storageKey && event.key === storageKey) { state = load(); updateClock(); }
  }, {signal});
  document.addEventListener('visibilitychange', tick, {signal});
  window.addEventListener('focus', tick, {signal});
  const interval = setInterval(tick, 250);
  tick();
  return () => { clearInterval(interval); events.abort(); initialized = false; };
}

export function setPomodoroUser(userId) {
  const nextKey = userId === null ? null : `${STORAGE_PREFIX}${userId}`;
  if (nextKey === storageKey) return;
  accountGeneration++;
  const previousKey = storageKey;
  if (previousKey) {
    state = load();
    if (state.running) pauseTimer(state);
    save();
    if ('serviceWorker' in navigator) {
      void navigator.serviceWorker.getRegistration().then(async registration => {
        const notifications = await registration?.getNotifications();
        notifications?.filter(item => item.tag.startsWith(`${previousKey}:`)).forEach(item => item.close());
      }).catch(() => {});
    }
  }
  liveNotifications.forEach(notification => notification.close());
  liveNotifications.clear();
  storageKey = nextKey;
  storageAvailable.value = true;
  state = storageKey ? load() : createState();
  latestAlert.value = null;
  dismissTimerAlert();
  updateClock();
  tick();
}
