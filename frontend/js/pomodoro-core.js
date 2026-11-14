// Timer state is independent of the DOM, storage, and browser notification APIs.
export const DEFAULT_SETTINGS = Object.freeze({study:25, short:5, long:15});
export const PHASE_NAMES = Object.freeze({study:'Study', short:'Short break', long:'Long break'});
const PHASES = Object.keys(DEFAULT_SETTINGS);

export function validateSettings(settings) {
  const result = {};
  for (const phase of PHASES) {
    const value = Number(settings[phase]);
    if (!Number.isFinite(value) || value < 0.01 || value > 180 || Math.abs(value * 100 - Math.round(value * 100)) > 0.000001) {
      throw new Error('Use 0.01–180 minutes, with up to two decimal places, for every timer.');
    }
    result[phase] = value;
  }
  return result;
}

export const durationMs = (settings, phase) => Math.round(settings[phase] * 60000);
export const nextTask = state => state.tasks.find(task => task.completed < task.target) || null;
export const currentTask = state => state.tasks.find(task => task.id === state.assignedTaskId) || nextTask(state);

export function createState() {
  return {version:1, settings:{...DEFAULT_SETTINGS}, phase:'study', intervalMs:1500000,
    remainingMs:1500000, deadline:null, running:false, awaitingStart:false, completedInCycle:0,
    totalPomodoros:0, assignedTaskId:null, tasks:[], lastNotice:null};
}

export function restoreState(saved) {
  if (!saved || saved.version !== 1) return createState();
  try {
    const settings = validateSettings(saved.settings);
    if (!PHASES.includes(saved.phase) || typeof saved.running !== 'boolean' ||
        (saved.awaitingStart !== undefined && typeof saved.awaitingStart !== 'boolean') ||
        (saved.awaitingStart && (saved.running || saved.remainingMs !== saved.intervalMs)) ||
        !Number.isFinite(saved.intervalMs) || saved.intervalMs < 600 || saved.intervalMs > 10800000 ||
        !Number.isFinite(saved.remainingMs) || saved.remainingMs < 0 || saved.remainingMs > saved.intervalMs ||
        (saved.running && !Number.isFinite(saved.deadline)) ||
        !Number.isSafeInteger(saved.completedInCycle) || saved.completedInCycle < 0 || saved.completedInCycle > 4 ||
        !Number.isSafeInteger(saved.totalPomodoros) || saved.totalPomodoros < 0 || !Array.isArray(saved.tasks)) {
      return createState();
    }
    const tasks = saved.tasks.map(task => {
      if (!task || typeof task.id !== 'string' || !task.id || typeof task.title !== 'string' ||
          !task.title.trim() || task.title.length > 160 || !Number.isSafeInteger(task.target) ||
          task.target < 1 || task.target > 99 || !Number.isSafeInteger(task.completed) ||
          task.completed < 0 || task.completed > task.target) throw new Error('Invalid saved task');
      return {id:task.id, title:task.title, target:task.target, completed:task.completed};
    });
    if (new Set(tasks.map(task => task.id)).size !== tasks.length) return createState();
    const assigned = tasks.find(task => task.id === saved.assignedTaskId && task.completed < task.target);
    if (saved.phase === 'study' && saved.completedInCycle === 4) return createState();
    return {version:1, settings, phase:saved.phase, intervalMs:saved.intervalMs,
      remainingMs:saved.remainingMs, deadline:saved.running ? saved.deadline : null,
      running:saved.running, awaitingStart:saved.awaitingStart === true, completedInCycle:saved.completedInCycle,
      totalPomodoros:saved.totalPomodoros,
      assignedTaskId:saved.phase === 'study' ? assigned?.id || null : null, tasks,
      lastNotice:saved.lastNotice && typeof saved.lastNotice.title === 'string' &&
        typeof saved.lastNotice.message === 'string' ? saved.lastNotice : null};
  } catch { return createState(); }
}

export function remainingMs(state, now = Date.now()) {
  return state.running ? Math.max(0, state.deadline - now) : state.remainingMs;
}

export function startTimer(state, now = Date.now()) {
  if (state.running) return;
  if (state.phase === 'study' && !state.assignedTaskId) state.assignedTaskId = nextTask(state)?.id || null;
  state.deadline = now + state.remainingMs;
  state.running = true;
  state.awaitingStart = false;
}

export function pauseTimer(state, now = Date.now()) {
  if (!state.running) return;
  state.remainingMs = remainingMs(state, now);
  state.deadline = null;
  state.running = false;
}

export function resetTimer(state) {
  state.running = false;
  state.deadline = null;
  state.awaitingStart = false;
  state.intervalMs = durationMs(state.settings, state.phase);
  state.remainingMs = state.intervalMs;
  state.assignedTaskId = null;
}

export function selectPhase(state, phase) {
  if (!PHASES.includes(phase)) throw new Error('Choose a valid timer mode.');
  if (state.phase === phase) return;
  state.phase = phase;
  if (phase === 'study' && state.completedInCycle === 4) state.completedInCycle = 0;
  resetTimer(state);
  state.lastNotice = null;
}

export function setSettings(state, settings) {
  const validated = validateSettings(settings);
  const untouched = !state.running && state.remainingMs === state.intervalMs;
  state.settings = validated;
  if (untouched) {
    const awaitingStart = state.awaitingStart;
    resetTimer(state);
    state.awaitingStart = awaitingStart;
  }
}

export function addTask(state, {id, title, target}) {
  if (typeof title !== 'string' || !title.trim() || title.trim().length > 160) throw new Error('Enter a task name of 1–160 characters.');
  if (!Number.isInteger(target) || target < 1 || target > 99) throw new Error('Choose 1–99 pomodoros for this task.');
  if (typeof id !== 'string' || !id || state.tasks.some(task => task.id === id)) throw new Error('This task could not be added. Try again.');
  state.tasks.push({id, title:title.trim(), target, completed:0});
}

export function removeTask(state, id) {
  if (state.assignedTaskId === id) throw new Error('Reset the current study timer before removing its task.');
  state.tasks = state.tasks.filter(task => task.id !== id);
}

export function advanceTimer(state, now = Date.now()) {
  if (!state.running || state.deadline > now) return null;
  const previousPhase = state.phase;
  let completedTask = null;
  if (previousPhase === 'study') {
    state.completedInCycle++;
    state.totalPomodoros++;
    const task = state.tasks.find(task => task.id === state.assignedTaskId);
    if (task && task.completed < task.target) {
      task.completed++;
      if (task.completed === task.target) completedTask = task;
    }
    state.phase = state.completedInCycle === 4 ? 'long' : 'short';
  } else {
    if (previousPhase === 'long' || state.completedInCycle === 4) state.completedInCycle = 0;
    state.phase = 'study';
  }
  const upcoming = nextTask(state);
  state.assignedTaskId = null;
  state.intervalMs = durationMs(state.settings, state.phase);
  state.remainingMs = state.intervalMs;
  // Credit only the interval that ran. The next phase needs an explicit Start.
  state.deadline = null;
  state.running = false;
  state.awaitingStart = true;
  const title = completedTask ? 'Task complete' : `${PHASE_NAMES[previousPhase]} finished`;
  let message = completedTask
    ? `“${completedTask.title}” completed (${completedTask.target}/${completedTask.target} pomodoros). ${upcoming ? `Moving on to “${upcoming.title}”.` : 'All tasks are complete. You can continue with free study.'} `
    : previousPhase === 'study' ? `Pomodoro ${state.completedInCycle} of 4 complete. ` : '';
  message += `${PHASE_NAMES[state.phase]} is ready: ${state.settings[state.phase]} minutes. Start when you’re ready.`;
  if (state.phase === 'study' && upcoming) message += ` Next task: ${upcoming.title}.`;
  state.lastNotice = {id:`${now}-${state.totalPomodoros}-${state.phase}`, title, message, at:now};
  return state.lastNotice;
}
