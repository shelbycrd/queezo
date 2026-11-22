import {test} from 'node:test';
import assert from 'node:assert/strict';
import {sharedAnswers, sharedChoices, shuffle} from '../js/shared-practice.js';

test('shared options preserve the original answer and use distinct deck answers', () => {
  const cards = ['  Blue  whale ', 'blue whale', '', 'Orca', 'Dolphin', 'Beluga'].map(back => ({back}));
  const answers = sharedAnswers(cards);
  assert.deepEqual(answers, ['  Blue  whale ', 'Orca', 'Dolphin', 'Beluga']);
  assert.deepEqual(new Set(sharedChoices('blue whale',answers)), new Set(['blue whale','Orca','Dolphin','Beluga']));
});

test('shared options do not fabricate choices for a deck with too few distinct answers', () => {
  const answers = sharedAnswers(['cat',' Cat ','dog','fish'].map(back => ({back})));
  assert.deepEqual(sharedChoices('Cat',answers), []);
});

test('shared practice shuffles a copy of the deck', () => {
  const cards = ['cat','dog','fish'];
  assert.deepEqual(shuffle(cards,() => 0), ['dog','fish','cat']);
  assert.deepEqual(cards, ['cat','dog','fish']);
});
