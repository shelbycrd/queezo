import test from 'node:test';
import assert from 'node:assert/strict';
import {api} from '../js/api.js';
import {authenticatedUser, authVersion, csrfToken, onUnauthorized, setAuthenticatedUser} from '../js/auth-state.js';

const user = {id:7, email:'student@example.test', csrf_token:'csrf-one'};

test('session and CSRF state are memory-only and version changes with the session', () => {
  const originalStorage = Object.getOwnPropertyDescriptor(globalThis, 'localStorage');
  Object.defineProperty(globalThis, 'localStorage', {configurable:true, get:() => { throw new Error('Auth must not touch localStorage'); }});
  try {
    setAuthenticatedUser(user);
    const before = authVersion();
    assert.equal(csrfToken(), 'csrf-one');
    assert.equal(authenticatedUser().email, 'student@example.test');
    setAuthenticatedUser({...user});
    assert.equal(authVersion(), before);
    setAuthenticatedUser({...user, csrf_token:'rotated'});
    assert.ok(authVersion() > before);
    setAuthenticatedUser(null);
    assert.equal(authenticatedUser(), null);
    assert.equal(csrfToken(), '');
  } finally {
    if (originalStorage) Object.defineProperty(globalThis, 'localStorage', originalStorage);
    else delete globalThis.localStorage;
    setAuthenticatedUser(null);
  }
});

test('cookie-authenticated mutations send CSRF while GET requests do not', async () => {
  setAuthenticatedUser(user);
  const originalFetch = globalThis.fetch;
  const requests = [];
  globalThis.fetch = async (url, options) => {
    requests.push({url, options});
    return new Response(JSON.stringify({ok:true}), {status:200});
  };
  try {
    await api('/gwa/calculate', {method:'POST', body:{courses:[]}});
    await api('/decks/1', {method:'PATCH', body:{title:'Topic'}});
    await api('/decks/1', {method:'DELETE'});
    await api('/decks');
    for (const request of requests.slice(0,3)) {
      assert.equal(request.options.headers['X-CSRF-Token'], 'csrf-one');
      assert.equal(request.options.credentials, 'same-origin');
      assert.equal(request.options.cache, 'no-store');
    }
    assert.equal(requests[3].options.headers['X-CSRF-Token'], undefined);
    assert.equal(requests[0].url, '/api/gwa/calculate');
    assert.equal(requests[0].options.headers['Content-Type'], 'application/json');
  } finally { globalThis.fetch = originalFetch; setAuthenticatedUser(null); }
});

test('401 academic responses expire the client session; failed login remains a form error', async () => {
  let expired = 0;
  onUnauthorized(() => expired++);
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async () => new Response(JSON.stringify({error:{message:'Invalid email or password.'}}), {status:401});
  try {
    await assert.rejects(api('/decks'), error => error.status === 401);
    assert.equal(expired, 1);
    await assert.rejects(api('/auth/login', {method:'POST', body:{email:'student@example.test', password:'wrong'}, ignoreUnauthorized:true}), error => error.status === 401);
    assert.equal(expired, 1);
    await assert.rejects(api('/auth/me', {ignoreUnauthorized:true}), error => error.status === 401);
    assert.equal(expired, 1);
  } finally { globalThis.fetch = originalFetch; onUnauthorized(() => {}); }
});

test('late responses from a previous account cannot reach academic page handlers', async () => {
  const originalFetch = globalThis.fetch;
  let resolve;
  globalThis.fetch = () => new Promise(done => { resolve = done; });
  try {
    for (const status of [200,204]) {
      setAuthenticatedUser(user);
      const pending = api('/decks', status === 204 ? {method:'DELETE'} : {});
      setAuthenticatedUser({id:8, email:'other@example.test', csrf_token:'other-token'});
      resolve(status === 204 ? new Response(null, {status}) : new Response(JSON.stringify([{title:'Private old account topic'}]), {status}));
      await assert.rejects(pending, error => error.status === 409 && !error.message.includes('Private'));
    }
  } finally { globalThis.fetch = originalFetch; setAuthenticatedUser(null); }
});

test('unauthenticated login sends cookies but never invents a CSRF credential', async () => {
  setAuthenticatedUser(null);
  const originalFetch = globalThis.fetch;
  let options;
  globalThis.fetch = async (_, value) => {
    options = value;
    return new Response(JSON.stringify(user), {status:200});
  };
  try {
    await api('/auth/login', {method:'POST', body:{email:user.email, password:'test password'}, ignoreUnauthorized:true});
    assert.equal(options.credentials, 'same-origin');
    assert.equal(options.headers['X-CSRF-Token'], undefined);
    assert.equal(csrfToken(), ''); // Only the auth controller adopts a validated response.
  } finally { globalThis.fetch = originalFetch; }
});
