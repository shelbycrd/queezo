import {test} from 'node:test';
import assert from 'node:assert/strict';
import {achievementProgress, sortedAchievements, unlockedDate} from '../src/services/achievements.js';

test('progress is shown only for locked achievements and clamps at the boundaries', () => {
  assert.deepEqual(achievementProgress({unlocked:false,progress:9,goal:10,scope:'lifetime'}),
    {value:9,goal:10,percent:90,label:'9 of 10'});
  assert.equal(achievementProgress({unlocked:false,progress:14,goal:10}).value,10);
  assert.equal(achievementProgress({unlocked:false,progress:-2,goal:6}).value,0);
  assert.equal(achievementProgress({unlocked:false,progress:3,goal:10,scope:'daily'}).label,'3 of 10 today');
  assert.equal(achievementProgress({unlocked:true,progress:10,goal:10}),null);
  // Visitor payloads carry no goal or progress, so nothing private can render.
  assert.equal(achievementProgress({unlocked:false,key:'hoster'}),null);
});

test('unlock dates render only from valid timestamps', () => {
  assert.match(unlockedDate({unlocked_at:'2026-11-20T08:00:00Z'}),/2026/);
  assert.equal(unlockedDate({}),'');
  assert.equal(unlockedDate({unlocked_at:'not a date'}),'');
});

test('earned achievements are listed first in catalog order', () => {
  const items = [{key:'deck_master',unlocked:false},{key:'studious',unlocked:true},{key:'hoster',unlocked:true}];
  assert.deepEqual(sortedAchievements(items).map(item => item.key),['studious','hoster','deck_master']);
  assert.deepEqual(sortedAchievements(undefined),[]);
});
