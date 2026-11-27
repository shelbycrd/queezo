import {test} from 'node:test';
import assert from 'node:assert/strict';
import {passwordChangeProblem} from '../src/services/password-change.js';

const valid = {current:'Current-password-1', replacement:'Brand-new-password-2', confirm:'Brand-new-password-2'};

test('a complete, matching, different password passes', () => {
  assert.equal(passwordChangeProblem(valid), '');
  assert.equal(passwordChangeProblem({...valid, replacement:'x'.repeat(11), confirm:'x'.repeat(11)}), '');
});

test('each problem gets a clear message before anything is sent', () => {
  assert.equal(passwordChangeProblem({...valid, current:''}), 'Enter your current password.');
  assert.equal(passwordChangeProblem({...valid, replacement:''}), 'Enter a new password.');
  assert.equal(passwordChangeProblem({...valid, replacement:'short', confirm:'short'}), 'Passwords must contain 11–1024 characters.');
  assert.equal(passwordChangeProblem({...valid, replacement:'x'.repeat(1025), confirm:'x'.repeat(1025)}), 'Passwords must contain 11–1024 characters.');
  assert.equal(passwordChangeProblem({...valid, confirm:'Brand-new-password-3'}), 'New password and confirmation do not match.');
  assert.equal(passwordChangeProblem({...valid, replacement:valid.current, confirm:valid.current}), 'Choose a password different from your current one.');
});
