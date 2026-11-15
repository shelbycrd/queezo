import test from 'node:test';
import assert from 'node:assert/strict';
import {passwordStrength} from '../js/password-strength.js';

test('advisory meter distinguishes empty, weak, moderate, and strong passwords', () => {
  assert.equal(passwordStrength('').score,0);
  assert.equal(passwordStrength('password123').level,'Low');
  assert.equal(passwordStrength('xxxxxxxxxxxxxxxx').level,'Low');
  assert.equal(passwordStrength('StudyRoom134').level,'Moderate');
  assert.equal(passwordStrength('QuietCloud!73Maple').level,'Strong');
});
test('sequences and personal details reduce the estimate without imposing registration rules', () => {
  const sequence = passwordStrength('Abcd!2468Zxcv');
  assert.ok(sequence.score <= 55);
  assert.ok(sequence.tips.some(tip=>tip.includes('consecutive')));
  const personal = passwordStrength('QuietCloud!73Maple',['QuietCloud']);
  assert.ok(personal.score <= 55);
  assert.ok(personal.tips.some(tip=>tip.includes('display name')));
});
