import test from 'node:test';
import assert from 'node:assert/strict';
import {addTask, advanceTimer, createState, currentTask, durationMs, nextTask, pauseTimer,
  remainingMs, removeTask, resetTimer, restoreState, setSettings, startTimer,
  selectPhase, skipPhase, validateSettings} from '../js/pomodoro-core.js';

// Simulate the user's explicit Start for every new phase in cycle tests.
function finishPhase(state) {
  startTimer(state, 0);
  return advanceTimer(state, state.deadline);
}

test('default cycle follows 25/5/25/5/25/5/25/15 and repeats', () => {
  const state = createState();
  const seen = [];
  startTimer(state, 0);
  for (let i = 0; i < 16; i++) {
    seen.push([state.phase, state.intervalMs / 60000]);
    assert.ok(finishPhase(state));
    assert.equal(state.running, false);
    assert.equal(state.awaitingStart, true);
  }
  const cycle = [['study',25],['short',5],['study',25],['short',5],['study',25],['short',5],['study',25],['long',15]];
  assert.deepEqual(seen, [...cycle,...cycle]);
  assert.equal(state.totalPomodoros, 8);
  assert.equal(state.completedInCycle, 0);
  assert.equal(state.phase, 'study');
  assert.equal(state.running, false);
});

test('only completed study intervals count toward tasks and advancement needs no confirmation', () => {
  const state = createState();
  addTask(state, {id:'assignment', title:'Do assignment', target:2});
  addTask(state, {id:'reading', title:'Read a chapter', target:1});
  startTimer(state, 0);
  finishPhase(state);
  assert.equal(state.tasks[0].completed, 1);
  assert.equal(state.tasks[1].completed, 0);
  assert.equal(state.phase, 'short');
  finishPhase(state);
  assert.equal(state.tasks[0].completed, 1);
  assert.equal(state.assignedTaskId, null);
  const event = finishPhase(state);
  assert.equal(state.tasks[0].completed, 2);
  assert.equal(nextTask(state).id, 'reading');
  assert.equal(event.title, 'Task complete');
  assert.match(event.message, /Do assignment.*2\/2.*Moving on to.*Read a chapter/);
  assert.equal(state.running, false);
  finishPhase(state);
  assert.equal(state.assignedTaskId, null);
  const final = finishPhase(state);
  assert.match(final.message, /All tasks are complete/);
  assert.equal(nextTask(state), null);
  assert.equal(state.running, false);
});

test('task targets cross cycle boundaries without being reset', () => {
  const state = createState();
  addTask(state, {id:'long', title:'Long assignment', target:5});
  startTimer(state, 0);
  for (let i = 0; i < 8; i++) finishPhase(state);
  assert.equal(state.tasks[0].completed, 4);
  assert.equal(state.completedInCycle, 0);
  assert.equal(state.assignedTaskId, null);
  finishPhase(state);
  assert.equal(state.tasks[0].completed, 5);
  assert.equal(nextTask(state), null);
});

test('wall-clock deadlines, pause, and resume retain exact remaining time', () => {
  const state = createState();
  startTimer(state, 1000);
  assert.equal(remainingMs(state, 41000), 1460000);
  pauseTimer(state, 41000);
  assert.equal(remainingMs(state, 9000000), 1460000);
  assert.equal(advanceTimer(state, 9000000), null);
  startTimer(state, 10000000);
  assert.equal(state.deadline, 11460000);
  assert.equal(advanceTimer(state, 11459999), null);
  assert.ok(advanceTimer(state, 11460000));
  assert.equal(state.totalPomodoros, 1);
});

test('duplicate completion checks do not double-credit or double-notify', () => {
  const state = createState();
  addTask(state, {id:'task', title:'Task', target:2});
  startTimer(state, 0);
  const deadline = state.deadline;
  assert.ok(advanceTimer(state, deadline));
  assert.equal(advanceTimer(state, deadline), null);
  const saved = restoreState(JSON.parse(JSON.stringify(state)));
  assert.equal(advanceTimer(saved, deadline), null);
  assert.equal(saved.tasks[0].completed, 1);
  assert.equal(saved.totalPomodoros, 1);
});

test('refresh preserves an active task, deadline, settings, and progress', () => {
  const state = createState();
  setSettings(state, {study:0.05, short:0.02, long:0.03});
  addTask(state, {id:'task', title:'Task', target:2});
  startTimer(state, 100);
  const saved = restoreState(JSON.parse(JSON.stringify(state)));
  assert.equal(saved.deadline, 3100);
  assert.equal(saved.assignedTaskId, 'task');
  assert.equal(remainingMs(saved, 1100), 2000);
  advanceTimer(saved, 3100);
  assert.equal(saved.tasks[0].completed, 1);
  assert.equal(saved.intervalMs, 1200);
});

test('late browser wake-up credits one actual interval, not fabricated overnight cycles', () => {
  const state = createState();
  startTimer(state, 0);
  const now = 24 * 60 * 60 * 1000;
  const event = advanceTimer(state, now);
  assert.equal(event.title, 'Study finished');
  assert.equal(state.totalPomodoros, 1);
  assert.equal(state.phase, 'short');
  assert.equal(state.deadline, null);
  assert.equal(state.remainingMs, 5 * 60000);
  assert.equal(state.awaitingStart, true);
  assert.equal(advanceTimer(state, now), null);
});

test('every phase waits indefinitely for Start, including after refresh, without extra credit', () => {
  for (const phase of ['study','short','long']) {
    const state = createState();
    if (phase !== 'study') selectPhase(state, phase);
    addTask(state, {id:'task',title:'Review',target:2});
    startTimer(state, 0);
    advanceTimer(state, state.deadline);
    const saved = restoreState(JSON.parse(JSON.stringify(state)));
    assert.equal(saved.awaitingStart, true);
    assert.equal(saved.running, false);
    assert.equal(saved.deadline, null);
    const before = JSON.stringify(saved);
    assert.equal(advanceTimer(saved, 999999999), null);
    assert.equal(JSON.stringify(saved), before);
    assert.equal(saved.totalPomodoros, phase === 'study' ? 1 : 0);
    startTimer(saved, 1000000000);
    assert.equal(saved.awaitingStart, false);
    assert.equal(saved.running, true);
    assert.equal(saved.deadline, 1000000000 + saved.intervalMs);
    pauseTimer(saved, 1000000100);
    assert.equal(saved.remainingMs, saved.intervalMs - 100);
    assert.equal(saved.awaitingStart, false);
  }
});

test('waiting keeps its prompt through settings changes, reset clears it, and older saves still restore', () => {
  const state = createState();
  startTimer(state,0);
  advanceTimer(state,state.deadline);
  setSettings(state,{study:20,short:7,long:12});
  assert.equal(state.awaitingStart,true);
  assert.equal(state.remainingMs,420000);
  resetTimer(state);
  assert.equal(state.awaitingStart,false);
  const legacy = {...state};
  delete legacy.awaitingStart;
  assert.deepEqual(restoreState(legacy),state);
});

test('skip moves to the next phase without crediting skipped study or binding the next task early', () => {
  const state = createState();
  addTask(state,{id:'task',title:'Review notes',target:2});
  startTimer(state,0);
  pauseTimer(state,1000);
  skipPhase(state);
  assert.equal(state.phase,'short');
  assert.equal(state.running,false);
  assert.equal(state.awaitingStart,true);
  assert.equal(state.deadline,null);
  assert.equal(state.remainingMs,300000);
  assert.equal(state.assignedTaskId,null);
  assert.equal(state.tasks[0].completed,0);
  assert.equal(state.totalPomodoros,0);
  assert.equal(state.completedInCycle,0);
  assert.deepEqual(restoreState(JSON.parse(JSON.stringify(state))),state);
  skipPhase(state);
  assert.equal(state.phase,'study');
  assert.equal(state.assignedTaskId,null);
  startTimer(state,2000);
  assert.equal(state.assignedTaskId,'task');
  advanceTimer(state,state.deadline);
  assert.equal(state.tasks[0].completed,1);
  assert.equal(state.totalPomodoros,1);
});

test('skipping a long break resets the cycle while preserving all earned study credit', () => {
  const state = createState();
  for (let index=0;index<7;index++) finishPhase(state);
  assert.equal(state.phase,'long');
  assert.equal(state.completedInCycle,4);
  startTimer(state,100);
  skipPhase(state);
  assert.equal(state.phase,'study');
  assert.equal(state.completedInCycle,0);
  assert.equal(state.totalPomodoros,4);
  assert.equal(state.awaitingStart,true);
  assert.equal(state.remainingMs,1500000);
  assert.deepEqual(restoreState(state),state);
});

test('settings changes preserve active/partially paused intervals and apply on reset', () => {
  const state = createState();
  startTimer(state, 0);
  setSettings(state, {study:10, short:2, long:8});
  assert.equal(state.deadline, 1500000);
  assert.equal(state.intervalMs, 1500000);
  pauseTimer(state, 1000);
  setSettings(state, {study:12, short:3, long:9});
  assert.equal(state.remainingMs, 1499000);
  resetTimer(state);
  assert.equal(state.remainingMs, 720000);
  assert.equal(state.running, false);
  assert.equal(state.totalPomodoros, 0);
});

test('idle settings apply immediately and decimal durations round to exact milliseconds', () => {
  const state = createState();
  setSettings(state, {study:0.01, short:0.02, long:0.03});
  assert.equal(state.remainingMs, 600);
  assert.equal(durationMs(state.settings,'long'), 1800);
});

test('tasks added during free study start next study rather than receiving retroactive credit', () => {
  const state = createState();
  startTimer(state, 0);
  addTask(state, {id:'new', title:'New task', target:2});
  finishPhase(state);
  assert.equal(state.tasks[0].completed, 0);
  finishPhase(state);
  assert.equal(state.assignedTaskId, null);
  startTimer(state, 0);
  assert.equal(state.assignedTaskId, 'new');
  assert.equal(currentTask(state).id, 'new');
});

test('reset and removal never fabricate study credit; active task removal is guarded', () => {
  const state = createState();
  addTask(state, {id:'task', title:' Task ', target:2});
  startTimer(state, 0);
  assert.throws(() => removeTask(state, 'task'), /Reset/);
  resetTimer(state);
  assert.equal(state.tasks[0].completed, 0);
  assert.equal(state.totalPomodoros, 0);
  assert.equal(state.assignedTaskId, null);
  removeTask(state, 'task');
  assert.deepEqual(state.tasks, []);
});

for (const invalid of [0, -1, 181, Infinity, NaN, '', null, 'abc', 0.001, 1.234]) {
  test(`invalid timer duration ${String(invalid)} is rejected without changing settings`, () => {
    const state = createState();
    assert.throws(() => setSettings(state, {study:invalid, short:5, long:15}));
    assert.deepEqual(state.settings, {study:25, short:5, long:15});
  });
}

test('invalid task titles and targets are rejected without changing the queue', () => {
  const state = createState();
  for (const target of [0,-1,1.5,100,NaN,Infinity,true]) {
    assert.throws(() => addTask(state, {id:'task', title:'Task', target}));
  }
  for (const title of ['', '   ', 'x'.repeat(161), null]) {
    assert.throws(() => addTask(state, {id:'task', title, target:2}));
  }
  assert.equal(state.tasks.length, 0);
});

test('corrupt saved state is rejected without crashing the timer', () => {
  for (const value of [null, {}, {version:2}, {...createState(), tasks:[{}]},
    {...createState(), remainingMs:-1}, {...createState(), running:true, deadline:null},
    {...createState(), phase:'unknown', completedInCycle:0},
    {...createState(), phase:'study', completedInCycle:4}]) {
    assert.deepEqual(restoreState(value), createState());
  }
  assert.deepEqual(validateSettings({study:'25',short:'5',long:'15'}), {study:25,short:5,long:15});
});

test('manual modes reset unfinished time without credit and survive refresh', () => {
  const state = createState();
  addTask(state, {id:'task', title:'Read', target:2});
  startTimer(state, 0);
  for (const phase of ['short', 'long', 'study']) {
    selectPhase(state, phase);
    assert.equal(state.running, false);
    assert.equal(state.deadline, null);
    assert.equal(state.remainingMs, state.settings[phase] * 60000);
    assert.equal(state.assignedTaskId, null);
    assert.equal(state.totalPomodoros, 0);
    assert.equal(state.tasks[0].completed, 0);
    assert.deepEqual(restoreState(state), state);
    startTimer(state, 100);
  }
  const deadline = state.deadline;
  selectPhase(state, 'study');
  assert.equal(state.deadline, deadline);
  assert.throws(() => selectPhase(state, 'invalid'));
});

test('manually selected breaks return to study without crediting tasks or corrupting the cycle', () => {
  for (const phase of ['short','long']) {
    const state = createState();
    state.completedInCycle = 4;
    selectPhase(state, phase);
    startTimer(state, 0);
    advanceTimer(state, state.deadline);
    assert.equal(state.phase, 'study');
    assert.equal(state.completedInCycle, 0);
    assert.equal(state.totalPomodoros, 0);
    assert.deepEqual(restoreState(state), state);
  }
});
