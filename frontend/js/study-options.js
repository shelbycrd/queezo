import {authenticatedUser} from './auth-state.js';

export function validateTiming(mode, scope, amount) {
  if (mode === 'unlimited') return {mode:'unlimited'};
  const value = Number(amount);
  if (!['number','string'].includes(typeof amount) || mode !== 'timed' || !['question','deck'].includes(scope) || !Number.isInteger(value) || value < 1 || value > (scope === 'question' ? 3600 : 180)) throw new Error('Choose a whole number within the time limit.');
  return {mode, scope, seconds:value * (scope === 'deck' ? 60 : 1)};
}
const timingKey = sessionId => `queezo.study-timing.${authenticatedUser()?.id}.${sessionId}`;
const memory = new Map();
export function saveTiming(sessionId, timing) {
  memory.set(timingKey(sessionId), timing);
  try { sessionStorage.setItem(timingKey(sessionId), JSON.stringify(timing)); } catch { /* In-memory timing still works. */ }
}
export function loadTiming(sessionId) {
  try {
    const value = memory.get(timingKey(sessionId)) || JSON.parse(sessionStorage.getItem(timingKey(sessionId)));
    if (value?.mode === 'timed' && ['question','deck'].includes(value.scope) && Number.isFinite(value.seconds) && value.seconds >= 1 && value.seconds <= 10800 && (!value.deadline || Number.isFinite(value.deadline))) return value;
  } catch { /* Old sessions are unlimited. */ }
  return {mode:'unlimited'};
}
