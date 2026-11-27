import {test} from 'node:test';
import assert from 'node:assert/strict';
import {effectScope} from 'vue';
import {useNow} from '../src/composables/clock.js';
import {loadSchedule, saveSubject, schedule, setTimeFormat, timeFormat} from '../src/services/schedule-store.js';
import {account} from '../src/services/session.js';

test('the clock ticks on each minute boundary and stops when its view is torn down', t => {
  t.mock.timers.enable({apis:['setTimeout', 'Date'], now:new Date(2026, 10, 23, 9, 59, 30).getTime()});
  const scope = effectScope();
  const now = scope.run(() => useNow({target:null}));
  assert.deepEqual([now.value.getHours(), now.value.getMinutes()], [9, 59]);
  t.mock.timers.tick(15000); // still inside the minute
  assert.equal(now.value.getMinutes(), 59);
  t.mock.timers.tick(16000); // 10:00:01
  assert.deepEqual([now.value.getHours(), now.value.getMinutes()], [10, 0]);
  t.mock.timers.tick(60000);
  assert.equal(now.value.getMinutes(), 1);
  scope.stop();
  t.mock.timers.tick(180000);
  assert.equal(now.value.getMinutes(), 1);
});

test('a hidden tab catches up the moment it becomes visible', t => {
  t.mock.timers.enable({apis:['setTimeout', 'Date'], now:new Date(2026, 10, 23, 9, 0, 0).getTime()});
  const target = Object.assign(new EventTarget(), {hidden:true});
  const scope = effectScope();
  const now = scope.run(() => useNow({target}));
  t.mock.timers.setTime(new Date(2026, 10, 23, 9, 40, 0).getTime()); // timers were throttled while hidden
  target.dispatchEvent(new Event('visibilitychange'));
  assert.equal(now.value.getMinutes(), 0); // still hidden: no update
  target.hidden = false;
  target.dispatchEvent(new Event('visibilitychange'));
  assert.equal(now.value.getMinutes(), 40);
  scope.stop();
});

const snapshot = overrides => ({time_format:'12h', subjects:[], conflicts:[], ...overrides});
const reply = (body, status = 200) => async () => new Response(JSON.stringify(body), {status, headers:{'content-type':'application/json'}});

test('changing the time format applies at once, is saved, and reverts if saving fails', async () => {
  const original = globalThis.fetch;
  try {
    schedule.value = snapshot();
    const calls = [];
    globalThis.fetch = async (url, options) => { calls.push([url, options.method, options.body]); return reply({time_format:'24h'})(); };
    const pending = setTimeFormat('24h');
    assert.equal(timeFormat.value, '24h'); // optimistic: Home, editor and timetable switch immediately
    await pending;
    assert.deepEqual(calls, [['/api/schedule/preferences', 'PUT', '{"time_format":"24h"}']]);
    assert.equal(timeFormat.value, '24h');
    await setTimeFormat('24h'); // no change: no request
    assert.equal(calls.length, 1);
    globalThis.fetch = reply({error:{message:'Nope'}}, 500);
    await assert.rejects(setTimeFormat('12h'), /Nope/);
    assert.equal(timeFormat.value, '24h'); // reverted
  } finally { globalThis.fetch = original; schedule.value = null; }
});

test('a slow refresh cannot overwrite a newer save, and signing out clears the schedule', async () => {
  const original = globalThis.fetch;
  try {
    account.value = {id:1};
    let finishLoad;
    globalThis.fetch = () => new Promise(resolve => { finishLoad = () => resolve(new Response(JSON.stringify(snapshot()), {status:200})); });
    const load = loadSchedule();
    globalThis.fetch = reply({...snapshot({subjects:[{id:5, name:'Saved', meetings:[]}]}), subject_id:5, warnings:[]}, 201);
    const result = await saveSubject(null, {name:'Saved'});
    assert.deepEqual([result.subjectId, result.warnings], [5, []]);
    finishLoad();
    await load;
    assert.deepEqual(schedule.value.subjects.map(item => item.name), ['Saved']); // the stale empty list was ignored
    account.value = null;
    await new Promise(resolve => setTimeout(resolve, 0));
    assert.equal(schedule.value, null);
  } finally { globalThis.fetch = original; account.value = null; schedule.value = null; }
});
