import {test} from 'node:test';
import assert from 'node:assert/strict';
import {shuffle} from '../js/shared-practice.js';

test('shared practice shuffles a copy of the deck', () => {
  const cards = ['cat','dog','fish'];
  assert.deepEqual(shuffle(cards,() => 0), ['dog','fish','cat']);
  assert.deepEqual(cards, ['cat','dog','fish']);
});
