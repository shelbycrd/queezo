import test from 'node:test';
import assert from 'node:assert/strict';
import {highestStreak} from '../js/profile-data.js';

test('highest streak counts the longest run rather than the latest run', () => {
  assert.equal(highestStreak(['2026-11-01','2026-11-02','2026-11-03','2026-11-10']), 3);
  assert.equal(highestStreak([]), 0);
});
test('streaks deduplicate activity and cross month and year boundaries', () => {
  assert.equal(highestStreak(['2027-01-01','2026-12-30','2026-12-31','2026-12-31']), 3);
  assert.equal(highestStreak(['2024-02-28','2024-02-29','2024-03-01']), 3);
});
