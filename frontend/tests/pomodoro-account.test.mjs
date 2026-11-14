import test from 'node:test';
import assert from 'node:assert/strict';
import {addTask, createState, setSettings, startTimer} from '../js/pomodoro-core.js';

test('Pomodoro uses separate account stores, pauses on logout, and never adopts anonymous legacy tasks', async () => {
  const originals = Object.fromEntries(['document','localStorage','navigator'].map(name => [name,Object.getOwnPropertyDescriptor(globalThis,name)]));
  const first = createState();
  addTask(first, {id:'a',title:'Private account A assignment',target:2});
  startTimer(first, Date.now());
  const second = createState();
  setSettings(second, {study:10,short:3,long:8});
  addTask(second, {id:'b',title:'Private account B assignment',target:1});
  const stored = new Map([
    ['queezo.pomodoro.v1', JSON.stringify({privateLegacy:'Unassigned anonymous content'})],
    ['queezo.pomodoro.v1.user.1', JSON.stringify(first)],
    ['queezo.pomodoro.v1.user.2', JSON.stringify(second)],
  ]);
  const reads = [];
  const clock = {textContent:''};
  const bannerText = {textContent:'Private alert'};
  const banner = {hidden:false,querySelector:() => bannerText};
  Object.defineProperty(globalThis,'document',{configurable:true,value:{title:'',querySelector:selector => selector === '#pomodoro-alert' ? banner : selector === '#pomodoro-time' ? clock : selector === '#pomodoro-progress' ? {} : null}});
  Object.defineProperty(globalThis,'navigator',{configurable:true,value:{}});
  Object.defineProperty(globalThis,'localStorage',{configurable:true,value:{getItem:key => { reads.push(key); return stored.get(key) ?? null; },setItem:(key,value) => stored.set(key,value)}});
  try {
    const {setPomodoroUser} = await import('../js/pomodoro.js');
    setPomodoroUser(1);
    assert.match(clock.textContent, /^2[45]:/);
    setPomodoroUser(2);
    assert.equal(clock.textContent, '10:00');
    const pausedA = JSON.parse(stored.get('queezo.pomodoro.v1.user.1'));
    assert.equal(pausedA.running, false);
    assert.equal(pausedA.tasks[0].title, 'Private account A assignment');
    assert.equal(JSON.parse(stored.get('queezo.pomodoro.v1.user.2')).tasks[0].title, 'Private account B assignment');
    setPomodoroUser(null);
    assert.equal(banner.hidden, true);
    assert.equal(bannerText.textContent, '');
    assert.equal(clock.textContent, '25:00');
    assert.equal(reads.includes('queezo.pomodoro.v1'), false);
    assert.equal(JSON.parse(stored.get('queezo.pomodoro.v1')).privateLegacy, 'Unassigned anonymous content');
  } finally {
    for (const [name,descriptor] of Object.entries(originals)) {
      if (descriptor) Object.defineProperty(globalThis,name,descriptor);
      else delete globalThis[name];
    }
  }
});

test('an account switch closes a persistent toast that finishes creating after logout cleanup', async () => {
  const names = ['document','localStorage','navigator','window','Notification'];
  const originals = Object.fromEntries(names.map(name => [name,Object.getOwnPropertyDescriptor(globalThis,name)]));
  const first = createState();
  addTask(first, {id:'private-task',title:'Private prior-account assignment',target:1});
  startTimer(first, Date.now() - 1501000);
  const stored = new Map([
    ['queezo.pomodoro.v1.user.7', JSON.stringify(first)],
    ['queezo.pomodoro.v1.user.8', JSON.stringify(createState())],
  ]);
  let finishCreation;
  let creationStarted;
  const started = new Promise(resolve => { creationStarted = resolve; });
  let displayed = false;
  let closes = 0;
  const tagLookups = [];
  const toast = {tag:'',close:() => { displayed = false; closes++; }};
  const registration = {
    active:true,
    showNotification:async (title, options) => {
      assert.match(options.body, /Private prior-account assignment/);
      toast.tag = options.tag;
      creationStarted();
      await new Promise(resolve => { finishCreation = resolve; });
      displayed = true;
    },
    getNotifications:async options => {
      if (options?.tag) tagLookups.push(options.tag);
      return displayed ? [toast] : [];
    },
  };
  const banner = {hidden:true,querySelector:() => ({textContent:''})};
  Object.defineProperty(globalThis,'document',{configurable:true,value:{title:'',querySelector:selector => selector === '#pomodoro-alert' ? banner : null}});
  Object.defineProperty(globalThis,'navigator',{configurable:true,value:{serviceWorker:{getRegistration:async () => registration}}});
  Object.defineProperty(globalThis,'window',{configurable:true,value:{Notification:{},isSecureContext:true}});
  Object.defineProperty(globalThis,'Notification',{configurable:true,value:{permission:'granted'}});
  Object.defineProperty(globalThis,'localStorage',{configurable:true,value:{getItem:key => stored.get(key) ?? null,setItem:(key,value) => stored.set(key,value)}});
  try {
    const {setPomodoroUser} = await import('../js/pomodoro.js');
    setPomodoroUser(7);
    await started;
    setPomodoroUser(8);
    // Let account-switch cleanup finish while the OS toast is not yet visible.
    await new Promise(resolve => setImmediate(resolve));
    assert.equal(closes, 0);
    finishCreation();
    await new Promise(resolve => setImmediate(resolve));
    assert.equal(displayed, false);
    assert.equal(closes, 1);
    assert.deepEqual(tagLookups, [toast.tag]);
    assert.match(toast.tag, /^queezo\.pomodoro\.v1\.user\.7:/);
    setPomodoroUser(null);
  } finally {
    for (const [name,descriptor] of Object.entries(originals)) {
      if (descriptor) Object.defineProperty(globalThis,name,descriptor);
      else delete globalThis[name];
    }
  }
});
