import test from 'node:test';
import assert from 'node:assert/strict';
import {ApiError} from '../js/api.js';
import {multipleChoiceSession, scoreSummary} from '../js/multiple-choice-session.js';

const path = '/multiple-choice/test';
const question = {id:'first', front:'Question', options:[
  {id:'a',text:'A'},{id:'b',text:'B'},{id:'c',text:'C'},{id:'d',text:'D'},
]};

function session(status, {ready = 0, failed = 0, answered = 0, correct = 0} = {}) {
  return {status, answered, correct, progress:{ready, failed, completed:ready+failed, total:2}};
}

function fixture(request, {expectedDelay = 1500, now = Date.now} = {}) {
  const updates = [], calls = [], timers = new Map();
  let id = 0;
  const controller = multipleChoiceSession('test', {
    update: value => updates.push(value),
    request: (url, options) => { calls.push([url,options]); return request(url,options); },
    setTimer: (fn, delay) => { assert.equal(delay, expectedDelay); timers.set(++id,fn); return id; },
    now,
    clearTimer: key => timers.delete(key),
  });
  return {
    controller, calls, timers, updates, latest: () => updates.at(-1),
    async poll() {
      assert.equal(timers.size, 1);
      const [key, fn] = timers.entries().next().value;
      timers.delete(key);
      fn();
      await new Promise(resolve => setImmediate(resolve));
    },
  };
}

test('preparation polls actual progress, fetches the question only once active, and stops polling', async () => {
  const states = [session('preparing'), session('preparing',{ready:1}), session('active',{ready:2})];
  const f = fixture(async url => url.endsWith('/question') ? question : states.shift());
  await f.controller.refresh();
  assert.equal(f.latest().session.progress.completed, 0);
  assert.equal(f.latest().question, null);
  await f.poll();
  assert.equal(f.latest().session.progress.completed, 1);
  await f.poll();
  assert.equal(f.latest().question, question);
  assert.equal(f.timers.size, 0);
  assert.deepEqual(f.calls.map(([url]) => url), [path,path,path,path+'/question']);
});

test('duplicate answer clicks are blocked and only the server result supplies the grade', async () => {
  let resolveGrade;
  const answer = new Promise(resolve => { resolveGrade = resolve; });
  const f = fixture(async url => url === path ? session('active',{ready:1,failed:1}) :
    url.endsWith('/question') ? question : answer);
  await f.controller.refresh();
  await f.controller.answer('foreign-option');
  const pending = f.controller.answer('d');
  await f.controller.answer('d');
  assert.equal(f.latest().grade, null);
  assert.equal(f.latest().pending, 'answer');
  assert.deepEqual(f.calls.at(-1), [path+'/answer',{method:'POST',body:{question_id:'first',option_id:'d'}}]);
  assert.equal(f.calls.length, 3);
  const graded = {session:session('completed',{ready:1,failed:1,answered:1}), is_correct:false,
    question_id:'first', selected_option_id:'d', correct_option:question.options[1]};
  resolveGrade(graded);
  await pending;
  assert.equal(f.latest().grade, graded);
  assert.equal(f.latest().question, question);
  f.controller.next();
  assert.equal(f.latest().grade,null);
  assert.equal(f.latest().session.status,'completed');
  assert.deepEqual(scoreSummary(f.latest().session), {correct:0,incorrect:1,total:1,accuracy:0});
});

test('conflict reloads the latest question instead of showing a fabricated grade', async () => {
  let answered = 0;
  const f = fixture(async url => {
    if (url.endsWith('/answer')) { answered = 1; throw new ApiError('Already answered',409); }
    return url === path ? session('active',{ready:2,answered}) :
      answered ? {...question,id:'second'} : question;
  });
  await f.controller.refresh();
  await f.controller.answer('a');
  assert.equal(f.latest().grade,null);
  assert.equal(f.latest().question.id,'second');
  assert.equal(f.latest().session.answered,1);
  assert.match(f.latest().message,/latest saved progress/);
});

test('network errors pause polling until an explicit refresh, and expiry is terminal', async () => {
  let requests = 0;
  const f = fixture(async () => {
    if (++requests === 2) throw new ApiError('Offline',0);
    return session(requests === 1 ? 'preparing' : 'expired');
  });
  await f.controller.refresh();
  await f.poll();
  assert.equal(f.latest().problem.status,0);
  assert.equal(f.timers.size,0);
  await f.controller.refresh();
  assert.equal(f.latest().session.status,'expired');
  assert.equal(f.timers.size,0);
});

test('failure can retry, continue with ready questions, or cancel through the existing API', async () => {
  const partial = session('failed',{ready:1,failed:1});
  const f = fixture(async url => {
    if (url.endsWith('/retry')) return session('preparing',{ready:1});
    if (url.endsWith('/continue')) return session('active',{ready:1,failed:1});
    if (url.endsWith('/cancel')) return session('cancelled',{ready:1,failed:1});
    if (url.endsWith('/question')) return question;
    return partial;
  });
  await f.controller.refresh();
  assert.equal(f.timers.size, 0);
  await f.controller.transition('retry');
  assert.equal(f.latest().session.status, 'preparing');
  await f.poll();
  await f.controller.transition('continue');
  assert.equal(f.latest().question,question);
  await f.controller.transition('cancel');
  assert.equal(f.latest().session.status,'cancelled');
  assert.equal(f.latest().question,null);
  assert.equal(f.timers.size,0);
  assert.deepEqual(f.calls.filter(([, options]) => options.method === 'POST').map(([url]) => url),
    [path+'/retry',path+'/continue',path+'/cancel']);
});

test('a per-question timeout opens the next question and reports the missed answer', async () => {
  let opened = 0;
  const initial = {...session('active',{ready:2}), timing:{scope:'question', seconds:3}, timed_out:0};
  const afterTimeout = {...initial, timed_out:1};
  const f = fixture(async (url, options) => {
    if (url === path) return initial;
    assert.equal(options.method, 'POST');
    if (++opened === 1) return {session:initial, question, remaining_ms:3000};
    return {session:afterTimeout, question:{...question,id:'second'}, remaining_ms:3000};
  }, {expectedDelay:3000, now:() => 10000});
  await f.controller.refresh();
  assert.equal(f.latest().clock,13000);
  await f.poll();
  assert.equal(f.latest().question.id,'second');
  assert.equal(f.latest().session.timed_out,1);
  assert.match(f.latest().message,/skipped/);
  f.controller.stop();
  assert.equal(f.timers.size,0);
});

test('a deck deadline remains scheduled during answer feedback', async () => {
  const initial = {...session('active',{ready:2}), timing:{scope:'deck', seconds:4}, timed_out:0};
  const graded = {...initial, answered:1, correct:1};
  let finished = false;
  const f = fixture(async url => {
    if (url === path) return finished ? {...graded,status:'completed',timed_out:1} : initial;
    if (url.endsWith('/answer')) return {session:graded, is_correct:true};
    return {session:initial, question, remaining_ms:4000};
  }, {expectedDelay:4000, now:() => 10000});
  await f.controller.refresh();
  await f.controller.answer('a');
  assert.ok(f.latest().grade);
  finished = true;
  await f.poll();
  assert.equal(f.latest().session.status,'completed');
  assert.equal(f.latest().grade,null);
  assert.equal(f.timers.size,0);
  assert.equal(scoreSummary(f.latest().session).accuracy,50);
});

test('leaving stops polling, aborts reads, and discards a late response', async () => {
  let resolveStatus;
  const f = fixture(() => new Promise(resolve => { resolveStatus = resolve; }));
  const pending = f.controller.refresh();
  f.controller.stop();
  assert.equal(f.calls[0][1].signal.aborted,true);
  resolveStatus(session('preparing'));
  await pending;
  assert.equal(f.updates.length,1);
  assert.equal(f.timers.size,0);
});
