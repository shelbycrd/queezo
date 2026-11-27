import {test} from 'node:test';
import assert from 'node:assert/strict';
import {greeting, sortFriends} from '../src/services/home.js';

const at = (hour, minute = 0) => new Date(2026, 10, 27, hour, minute);

test('greeting follows the browser-local hour at each boundary', () => {
  assert.equal(greeting(at(4, 59)), 'Good evening');
  assert.equal(greeting(at(5)), 'Good morning');
  assert.equal(greeting(at(11, 59)), 'Good morning');
  assert.equal(greeting(at(12)), 'Good afternoon');
  assert.equal(greeting(at(17, 59)), 'Good afternoon');
  assert.equal(greeting(at(18)), 'Good evening');
  assert.equal(greeting(at(0)), 'Good evening');
});

test('friends list shows online friends first, then by name, without mutating input', () => {
  const input = [{display_name:'Zed', online:true}, {display_name:'Amy', online:false}, {display_name:'Bea', online:true}];
  assert.deepEqual(sortFriends(input).map(friend => friend.display_name), ['Bea', 'Zed', 'Amy']);
  assert.equal(input[0].display_name, 'Zed');
  assert.deepEqual(sortFriends(), []);
});
