import {app, escape, mount} from './ui.js';
import {api} from './api.js';
import {addTask, advanceTimer, createState, currentTask, nextTask, pauseTimer, PHASE_NAMES,
  remainingMs, removeTask, resetTimer, restoreState, setSettings, startTimer} from './pomodoro-core.js';

const STORAGE_PREFIX = 'queezo.pomodoro.v1.user.';
let storageKey = null;
let accountGeneration = 0;
const liveNotifications = new Set();
let state = createState();
let initialized = false;
let renderPage = () => {};
let storageAvailable = true;
let serial = Promise.resolve();

function load() {
  if (!storageKey) return createState();
  try { return restoreState(JSON.parse(localStorage.getItem(storageKey))); }
  catch { return state; }
}

function save() {
  if (!storageKey) return;
  try { localStorage.setItem(storageKey, JSON.stringify(state)); storageAvailable = true; }
  catch { storageAvailable = false; }
}

function clockText(milliseconds) {
  const seconds = Math.ceil(milliseconds / 1000);
  return `${String(Math.floor(seconds / 60)).padStart(2,'0')}:${String(seconds % 60).padStart(2,'0')}`;
}

function permissionStatus() {
  if (!('Notification' in window) || !window.isSecureContext) return 'unavailable';
  return Notification.permission;
}

async function notify(event, generation) {
  if (!storageKey || generation !== accountGeneration) return;
  const banner = document.querySelector('#pomodoro-alert');
  banner.querySelector('strong').textContent = event.title;
  banner.querySelector('p').textContent = event.message;
  banner.hidden = false;
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
        if (generation === accountGeneration && storageKey) { window.focus(); location.hash = '#pomodoro'; }
        notification.close();
      };
    }
  } catch { /* The in-app alert is always available if system alerts fail. */ }
}

function transact(action = () => {}, {skipOnCompletion = false} = {}) {
  const generation = accountGeneration;
  const key = storageKey;
  const operation = async () => {
    const update = () => {
      if (!key || storageKey !== key || generation !== accountGeneration) return;
      if (storageAvailable) state = load();
      const previousPomodoros = state.totalPomodoros;
      const event = advanceTimer(state);
      let failure;
      try { if (!event || !skipOnCompletion) action(state); } catch (error) { failure = error; }
      // Commit a completed interval even if the following user action is invalid.
      save(); renderPage(); updateClock();
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
  const remaining = remainingMs(state);
  const display = document.querySelector('#pomodoro-time');
  if (display) {
    display.textContent = clockText(remaining);
    document.querySelector('#pomodoro-progress').value = state.intervalMs - Math.min(state.intervalMs, remaining);
  }
  const nav = document.querySelector('#pomodoro-nav-label') || document.querySelector('[data-nav="pomodoro"]');
  if (nav) nav.textContent = state.running ? `Pomodoro · ${clockText(remaining)}` : 'Pomodoro';
  document.title = state.running ? `${clockText(remaining)} · ${PHASE_NAMES[state.phase]} · Queezo` : 'Queezo · Study companion';
}

function tick() {
  if (!storageKey) return;
  if (state.running && state.deadline <= Date.now()) void transact();
  else updateClock();
}

export function initPomodoro() {
  if (initialized) return;
  initialized = true;
  document.querySelector('#dismiss-pomodoro-alert').addEventListener('click', () => {
    document.querySelector('#pomodoro-alert').hidden = true;
  });
  window.addEventListener('storage', event => {
    if (storageKey && event.key === storageKey) { state = load(); renderPage(); updateClock(); }
  });
  document.addEventListener('visibilitychange', tick);
  window.addEventListener('focus', tick);
  setInterval(tick, 250);
  tick();
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
  storageAvailable = true;
  state = storageKey ? load() : createState();
  renderPage = () => {};
  const banner = document.querySelector('#pomodoro-alert');
  banner.hidden = true;
  banner.querySelector('strong').textContent = '';
  banner.querySelector('p').textContent = '';
  updateClock();
  tick();
}

export function stopPomodoroView() { renderPage = () => {}; }

export function pomodoroPage(route) {
  if (!storageKey) return;
  if (!mount(`<div class="page-heading"><div><h1>Pomodoro</h1></div></div>
    <div class="pomodoro-layout pomodoro-focus-layout"><div class="pomodoro-main"><section class="panel timer-panel pomodoro-focus-timer" aria-label="Pomodoro timer">
      <div class="pomodoro-modes" aria-label="Timer intervals"><span class="pomodoro-mode" data-pomodoro-mode="study">Study</span><span class="pomodoro-mode" data-pomodoro-mode="short">Short break</span><span class="pomodoro-mode" data-pomodoro-mode="long">Long break</span></div>
      <div class="timer-top"><span id="pomodoro-phase" class="sr-only"></span><span id="pomodoro-state" class="muted"></span></div>
      <div id="pomodoro-time" class="pomodoro-time" role="timer" aria-label="Time remaining" aria-live="off">25:00</div>
      <progress id="pomodoro-progress" aria-label="Current timer progress" max="1500000" value="0"></progress>
      <p id="pomodoro-current" class="pomodoro-current"></p><div class="timer-actions"><button id="pomodoro-toggle" type="button">Start</button><button id="pomodoro-reset" type="button" class="secondary">Reset timer</button></div>
      <div class="cycle-info"><span id="pomodoro-cycle"></span><span id="pomodoro-total" class="muted"></span></div><div id="pomodoro-dots" class="pomodoro-dots" aria-label="Study sessions completed this cycle"></div>
      <p class="hint">Four study sessions, then a long break. Start each next phase when you’re ready.</p>
    </section>
    <details class="panel pomodoro-settings"><summary>Timer settings <span class="muted">minutes</span></summary><form id="pomodoro-settings-form"><div class="timer-settings-inputs">
      <div><label for="study-minutes">Study timer</label><input id="study-minutes" name="study" type="number" min="0.01" max="180" step="0.01" required value="${state.settings.study}"></div>
      <div><label for="short-minutes">Short break</label><input id="short-minutes" name="short" type="number" min="0.01" max="180" step="0.01" required value="${state.settings.short}"></div>
      <div><label for="long-minutes">Long break</label><input id="long-minutes" name="long" type="number" min="0.01" max="180" step="0.01" required value="${state.settings.long}"></div></div>
      <p class="hint">New durations apply to the next interval. Reset applies them to the current timer. You can use decimals for small timers.</p><button type="submit" class="secondary small">Save timers</button><p id="timer-settings-message" class="hint" role="status"></p></form></details>
    <section class="panel notification-panel"><h2>Timer alerts</h2><p id="notification-status" class="muted"></p><button id="enable-pomodoro-notifications" class="secondary small" type="button">Enable desktop notifications</button><p class="hint">Keep Queezo open. Your settings and tasks stay saved in this browser.</p><p id="pomodoro-storage-warning" class="inline-error" hidden>Browser storage is unavailable. Your timer and tasks will last only while this page stays open.</p></section></div>
    <section class="panel pomodoro-tasks"><div class="section-heading course-heading"><h2>Tasks</h2><span id="pomodoro-task-count" class="muted"></span></div><p class="hint">Set your pomodoros. We'll take care of moving to the next task.</p>
      <form id="pomodoro-task-form"><label for="pomodoro-task-title">Task</label><input id="pomodoro-task-title" name="title" maxlength="160" required placeholder="e.g. Do assignment">
        <div class="task-add-row"><div><label for="pomodoro-task-target">Pomodoros needed</label><input id="pomodoro-task-target" name="target" type="number" min="1" max="99" step="1" value="2" required></div><button type="submit">+ Add task</button></div></form>
      <p id="pomodoro-error" class="inline-error" role="alert" hidden></p><div id="pomodoro-task-list"></div>
    </section></div>`, route)) return;

  const toggle = app.querySelector('#pomodoro-toggle');
  const settingsForm = app.querySelector('#pomodoro-settings-form');
  const settingsMessage = app.querySelector('#timer-settings-message');
  const notificationStatus = app.querySelector('#notification-status');
  const tasksForm = app.querySelector('#pomodoro-task-form');
  const taskList = app.querySelector('#pomodoro-task-list');
  const error = app.querySelector('#pomodoro-error');
  let renderedTasks = '';

  function render() {
    if (location.hash !== route || !toggle.isConnected) return;
    app.querySelector('#pomodoro-phase').textContent = PHASE_NAMES[state.phase];
    app.querySelectorAll('[data-pomodoro-mode]').forEach(mode => {
      const active = mode.dataset.pomodoroMode === state.phase;
      mode.classList.toggle('active', active);
      if (active) mode.setAttribute('aria-current', 'true');
      else mode.removeAttribute('aria-current');
    });
    app.querySelector('#pomodoro-state').textContent = state.running ? 'Running' : state.awaitingStart ? 'Ready for the next phase' : state.remainingMs < state.intervalMs ? 'Paused' : 'Ready';
    toggle.textContent = state.running ? 'Pause' : state.awaitingStart ? `Start ${PHASE_NAMES[state.phase].toLowerCase()}` : state.remainingMs < state.intervalMs ? 'Resume' : 'Start';
    const task = state.phase === 'study' ? currentTask(state) : nextTask(state);
    const assigned = state.assignedTaskId && state.phase === 'study';
    app.querySelector('#pomodoro-current').textContent = task
      ? `${state.awaitingStart || state.phase !== 'study' || (state.running && !assigned) ? 'Up next' : 'Current task'}: ${task.title}`
      : 'Free study · add a task whenever you need one';
    app.querySelector('#pomodoro-progress').max = state.intervalMs;
    app.querySelector('#pomodoro-cycle').textContent = `${state.completedInCycle} of 4 study sessions complete`;
    app.querySelector('#pomodoro-total').textContent = `${state.totalPomodoros} total`;
    app.querySelector('#pomodoro-dots').innerHTML = [1,2,3,4].map(number => `<span class="pomodoro-dot ${number <= state.completedInCycle ? 'complete' : ''}">${number}</span>`).join('');
    const fingerprint = JSON.stringify([state.tasks, state.assignedTaskId, state.running, state.phase, state.awaitingStart]);
    if (fingerprint !== renderedTasks) {
      renderedTasks = fingerprint;
      taskList.innerHTML = state.tasks.length ? `<ol class="task-queue">${state.tasks.map(item => {
        const done = item.completed === item.target;
        const active = !done && task?.id === item.id;
        return `<li class="queued-task ${done ? 'task-done' : active ? 'task-active' : ''}"><div class="task-heading"><h3>${escape(item.title)}</h3><span class="badge">${done ? 'Done' : active ? state.phase === 'study' && !state.awaitingStart ? 'Current' : 'Next' : 'Queued'}</span></div><div class="task-progress-label"><span>${item.completed} / ${item.target} pomodoros</span><button type="button" class="remove-course" data-remove-task="${escape(item.id)}" ${state.assignedTaskId === item.id ? 'disabled title="Reset the study timer to remove this task"' : ''} aria-label="Remove task: ${escape(item.title)}">Remove</button></div><progress max="${item.target}" value="${item.completed}" aria-label="Progress for ${escape(item.title)}"></progress></li>`;
      }).join('')}</ol>` : '<div class="task-empty"><p>No tasks queued yet.</p><p class="hint">Add a task above or start a free study session.</p></div>';
    }
    app.querySelector('#pomodoro-task-count').textContent = `${state.tasks.filter(item => item.completed < item.target).length} remaining`;
    const permission = permissionStatus();
    const notificationButton = app.querySelector('#enable-pomodoro-notifications');
    notificationButton.hidden = permission === 'granted' || permission === 'unavailable' || permission === 'denied';
    app.querySelector('#notification-status').textContent = permission === 'granted'
      ? 'Desktop notifications are enabled. Queezo also shows an alert at every timer change.'
      : permission === 'denied' ? 'Desktop notifications are blocked in your browser. In-app alerts will still appear.'
      : permission === 'unavailable' ? 'Desktop notifications are unavailable in this browser. In-app alerts will still appear.'
      : 'In-app alerts are on. Enable desktop notifications to receive timer and task updates outside the page.';
    app.querySelector('#pomodoro-storage-warning').hidden = storageAvailable;
    updateClock();
  }

  async function act(action, options) {
    error.hidden = true;
    try { await transact(action, options); }
    catch (failure) { if (error.isConnected) { error.textContent = failure.message; error.hidden = false; } }
  }
  toggle.addEventListener('click', () => act(value => value.running ? pauseTimer(value) : startTimer(value), {skipOnCompletion:true}));
  app.querySelector('#pomodoro-reset').addEventListener('click', () => act(resetTimer));
  settingsForm.addEventListener('submit', async event => {
    event.preventDefault();
    if (!settingsForm.reportValidity()) return;
    try {
      await transact(value => setSettings(value, Object.fromEntries(new FormData(settingsForm))));
      settingsMessage.textContent = 'Timers saved. Reset to apply to this interval now.';
    } catch (failure) { settingsMessage.textContent = failure.message; }
  });
  tasksForm.addEventListener('submit', async event => {
    event.preventDefault();
    if (!tasksForm.reportValidity()) return;
    const title = tasksForm.elements.title.value;
    const target = Number(tasksForm.elements.target.value);
    const button = tasksForm.querySelector('button[type="submit"]');
    if (button.disabled) return;
    button.disabled = true;
    try {
      await act(value => {
        addTask(value, {id:crypto.randomUUID(), title, target});
        tasksForm.elements.title.value = '';
      });
    } finally { button.disabled = false; }
  });
  taskList.addEventListener('click', event => {
    const button = event.target.closest('[data-remove-task]');
    if (button) void act(value => removeTask(value, button.dataset.removeTask));
  });
  app.querySelector('#enable-pomodoro-notifications').addEventListener('click', async () => {
    try {
      // Permission is requested only in response to the user's explicit click.
      const permission = await Notification.requestPermission();
      if (permission === 'granted' && 'serviceWorker' in navigator) await navigator.serviceWorker.register('/pomodoro-worker.js');
      render();
    } catch { notificationStatus.textContent = 'Desktop alerts could not be enabled. In-app alerts remain on.'; }
  });
  renderPage = render;
  render();
  if (state.running && state.deadline <= Date.now()) void transact();
}
