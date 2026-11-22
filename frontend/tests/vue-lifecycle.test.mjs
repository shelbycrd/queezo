import test from 'node:test';
import assert from 'node:assert/strict';
import {effectScope} from 'vue';
import {useEvent,useResource} from '../src/composables/lifecycle.js';
import {chooseStudy,closeStudyOptions,studyRequest} from '../src/services/study-dialog.js';
import {notice,showNotice} from '../src/services/notice.js';

test('leaving a Vue view aborts its read and discards a late response', async () => {
  const scope = effectScope();
  let resolve, requestSignal;
  const status = scope.run(() => useResource(signal => {
    requestSignal = signal;
    return new Promise(done => { resolve = done; });
  }));
  scope.stop();
  assert.equal(requestSignal.aborted,true);
  resolve({result:'late'});
  await new Promise(done => setImmediate(done));
  assert.equal(status.data.value,null);
  assert.equal(status.error.value,'');
});

test('Vue view teardown removes global event callbacks', () => {
  const scope = effectScope(), target = new EventTarget();
  let calls = 0;
  scope.run(() => useEvent(target,'change',() => { calls++; }));
  target.dispatchEvent(new Event('change'));
  scope.stop();
  target.dispatchEvent(new Event('change'));
  assert.equal(calls,1);
});

test('study options have one active request and distinguish dismissal from starting', async () => {
  const original = chooseStudy(12);
  assert.equal(studyRequest.value.deckId,12);
  assert.equal(await chooseStudy(13),undefined);
  closeStudyOptions();
  assert.equal(await original,false);
  assert.equal(studyRequest.value,null);
  const retry = chooseStudy(13,{mode:'multiple-choice'});
  assert.equal(studyRequest.value.mode,'multiple-choice');
  closeStudyOptions(true);
  assert.equal(await retry,true);
});

test('notices are reactive state and reset without creating a second notice', () => {
  showNotice('Saved',true);
  assert.deepEqual(notice.value,{message:'Saved',success:true});
  showNotice('Try again');
  assert.deepEqual(notice.value,{message:'Try again',success:false});
  showNotice('');
  assert.equal(notice.value,null);
});
