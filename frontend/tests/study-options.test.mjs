import test from 'node:test';
import assert from 'node:assert/strict';
import {validateTiming, loadTiming, saveTiming} from '../js/study-options.js';
import {setAuthenticatedUser} from '../js/auth-state.js';
import {recentChats, validChats} from '../js/chat-data.js';

test('study modes validate bounded durations and convert deck minutes to seconds', () => {
  assert.deepEqual(validateTiming('unlimited','invalid',null),{mode:'unlimited'});
  assert.deepEqual(validateTiming('timed','question','30'),{mode:'timed',scope:'question',seconds:30});
  assert.equal(validateTiming('timed','deck','10').seconds,600);
  for (const value of [0,-1,1.5,Infinity,NaN,'',null,true,{},3601]) assert.throws(() => validateTiming('timed','question',value));
  assert.throws(() => validateTiming('timed','deck',181));
  assert.throws(() => validateTiming('timed','invalid',10));
});

test('saved study deadlines remain private to the active account and survive repeat reads', () => {
  setAuthenticatedUser({id:301,email:'a@example.com'});
  const timing = {mode:'timed',scope:'question',seconds:30,deadline:123456,presentation:2};
  saveTiming('test-session',timing);
  assert.deepEqual(loadTiming('test-session'),timing);
  setAuthenticatedUser({id:302,email:'b@example.com'});
  assert.deepEqual(loadTiming('test-session'),{mode:'unlimited'});
  setAuthenticatedUser({id:301,email:'a@example.com'});
  assert.deepEqual(loadTiming('test-session'),timing);
  setAuthenticatedUser(null);
});

test('chat previews reject malformed records and sort most recent activity first without changing storage order', () => {
  const chats = validChats([{id:'a',name:'First',updatedAt:1,messages:[{text:'Hello',at:1},null]},null,{id:'b',name:'Second',updatedAt:2,messages:[]},{id:'c',name:'',updatedAt:3,messages:[]}]);
  assert.equal(chats.length,2);
  assert.equal(chats[0].messages.length,1);
  assert.deepEqual(recentChats(chats).map(chat=>chat.id),['b','a']);
  chats[0].updatedAt=3;
  assert.deepEqual(recentChats(chats).map(chat=>chat.id),['a','b']);
  assert.deepEqual(validChats({}),[]);
});
