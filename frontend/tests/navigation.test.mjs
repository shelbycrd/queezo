import {test} from 'node:test';
import assert from 'node:assert/strict';
import {internalLinkPath, legacyHashPath} from '../src/services/navigation.js';

const base = 'http://localhost:8080/home';

test('old hash bookmarks become clean paths', () => {
  assert.equal(legacyHashPath('/','#/dashboard'),'/dashboard');
  assert.equal(legacyHashPath('/','#/rooms/2C9F10C8'),'/rooms/2C9F10C8');
  assert.equal(legacyHashPath('/','#/login?returnTo=/shared/abc'),'/login?returnTo=/shared/abc');
  assert.equal(legacyHashPath('/','#shared/token'),'/shared/token');
  assert.equal(legacyHashPath('/index.html','#/pomodoro'),'/pomodoro');
  assert.equal(legacyHashPath('/','#'),null);
  assert.equal(legacyHashPath('/','#/'),null);
  assert.equal(legacyHashPath('/home',''),null);
  assert.equal(legacyHashPath('/help','#section'),null);
});

test('same-origin app links route in the SPA while server paths and other sites load normally', () => {
  assert.equal(internalLinkPath('/flashcards',base),'/flashcards');
  assert.equal(internalLinkPath('/deck/4/edit/9?x=1',base),'/deck/4/edit/9?x=1');
  assert.equal(internalLinkPath('/#/gwa',base),'/gwa');
  assert.equal(internalLinkPath('http://localhost:8080/u/alice',base),'/u/alice');
  assert.equal(internalLinkPath('https://example.com/home',base),null);
  for (const path of ['/api/auth/me','/gwa/docs','/docs','/redoc','/openapi.json','/assets/queezo-cloud.svg']) {
    assert.equal(internalLinkPath(path,base),null,path);
  }
  assert.equal(internalLinkPath('#top',base),null);
  assert.equal(internalLinkPath('mailto:someone@example.com',base),null);
});
