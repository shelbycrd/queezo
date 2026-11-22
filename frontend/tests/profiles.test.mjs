import test from 'node:test';
import assert from 'node:assert/strict';
import {avatarUrl, avatars, deckPagePath,profileDraft,profilePath} from '../src/services/profiles.js';

test('avatar choices resolve only to bundled assets', () => {
  assert.deepEqual(avatars.map(avatarUrl), [
    '/assets/profile/dog.svg', '/assets/profile/cat.svg', '/assets/profile/chicken.svg',
  ]);
  assert.equal(avatarUrl('https://example.com/avatar'), '/assets/profile/cat.svg');
});

test('public profile links are clean and deck filters are encoded independently', () => {
  assert.equal(profilePath('student_1'),'/u/student_1');
  const path = new URL(deckPagePath('student_1',{q:' A & B ',sort:'alphabetical',page:2}),'http://localhost');
  assert.equal(path.pathname,'/profiles/users/student_1/decks');
  assert.deepEqual(Object.fromEntries(path.searchParams),{q:'A & B',sort:'alphabetical',page:'2'});
});

test('editing copies tags and sends only editable fields', () => {
  const profile = {
    username:'student_1', display_name:'Student', bio:'', interest_tags:['Mathematics'],
    avatar:'cat',visibility:'unlisted',featured_deck_id:null,email:'private@example.com',
    display_name_next_change_at:'2026-11-22T00:00:00Z',
  };
  const draft = profileDraft(profile);
  draft.interest_tags.push('Science');
  assert.deepEqual(profile.interest_tags,['Mathematics']);
  assert.deepEqual(draft,{
    display_name:'Student',bio:'',interest_tags:['Mathematics','Science'],
    avatar:'cat',visibility:'unlisted',featured_deck_id:null,
  });
});
