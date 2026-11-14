import assert from 'node:assert/strict';
import test from 'node:test';
import {formatGradeDisplay, normalizeGradeInput} from '../js/gwa-input.js';

test('three-digit grade shorthand converts as soon as complete', () => {
  for (const [raw, result] of [['175','1.75'],['225','2.25'],['100','1.00'],['500','5.00']]) {
    assert.equal(normalizeGradeInput(raw), result);
  }
});

test('partial grades, decimals and invalid shorthand are not silently rewritten', () => {
  for (const raw of ['', '1', '17', '1.75', '1.250001', '999', '501', '099', '-175']) {
    assert.equal(normalizeGradeInput(raw), raw);
  }
});

test('blur pads ordinary grades and preserves deliberate precision', () => {
  assert.equal(formatGradeDisplay('1'), '1.00');
  assert.equal(formatGradeDisplay('2.5'), '2.50');
  assert.equal(formatGradeDisplay('175'), '1.75');
  assert.equal(formatGradeDisplay('1.250001'), '1.250001');
  assert.equal(formatGradeDisplay('6'), '6');
});
