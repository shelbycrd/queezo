import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import test from 'node:test';
import {latestReleases, relativeDate, daysAgo} from '../src/services/changelog.js';
import {clearRecents, readRecents, recordVisit, visitRefForRoute, MAX_RECENT} from '../src/services/recent-visits.js';
import {normalizePage, normalizeQuery, normalizeTab, recentRequestPath, searchLocation, searchRequestPath} from '../src/services/global-search.js';

const read = path => readFileSync(new URL(path, import.meta.url), 'utf8');
const releases = JSON.parse(read('../src/data/changelog.json'));
const memory = () => { const data = new Map(); return {getItem:k => data.get(k) ?? null, setItem:(k, v) => data.set(k, String(v)), removeItem:k => data.delete(k), data}; };
const local = (y, m, d, h = 12, min = 0) => new Date(y, m - 1, d, h, min);

test('shipped changelog is real, well formed and parseable', () => {
  assert.ok(releases.length >= 4);
  const ids = new Set();
  for (const item of releases) {
    assert.ok(item.id && item.title && item.summary && !ids.has(item.id));
    ids.add(item.id);
    assert.ok(!Number.isNaN(new Date(item.date).getTime()), item.id);
    assert.match(item.date, /T\d\d:\d\d:\d\d[+-]\d\d:\d\d$/);
  }
});

test('changelog shows the four newest releases, newest first', () => {
  const now = local(2026, 11, 28);
  const shown = latestReleases(releases, now);
  assert.equal(shown.length, 4);
  const expected = [...releases].sort((a, b) => new Date(b.date) - new Date(a.date)).slice(0, 4).map(item => item.id);
  assert.deepEqual(shown.map(item => item.id), expected);
  const shuffled = latestReleases([releases[3], releases[0], releases[4], releases[1], releases[2]], now);
  assert.deepEqual(shuffled.map(item => item.id), expected);
});

test('changelog skips malformed and future entries and honours the limit', () => {
  const list = [
    {id:'a', title:'A', summary:'s', date:'2026-11-20T10:00:00+08:00'},
    {id:'bad', title:'B', summary:'s', date:'nope'},
    {id:'future', title:'F', summary:'s', date:'2027-01-01T00:00:00Z'},
    {id:'blank', title:'', summary:'s', date:'2026-11-21T00:00:00Z'},
  ];
  assert.deepEqual(latestReleases(list, local(2026, 11, 28)).map(item => item.id), ['a']);
  assert.equal(latestReleases(releases, local(2026, 11, 28), 2).length, 2);
});

test('relative dates use the viewer local calendar days', () => {
  const now = local(2026, 11, 28, 0, 5);
  assert.equal(relativeDate(local(2026, 11, 28, 0, 1), now), 'Today');
  assert.equal(relativeDate(local(2026, 11, 27, 23, 59), now), 'Yesterday'); // minutes earlier, but a different day
  assert.equal(relativeDate(local(2026, 11, 26, 8), now), '2 days ago');
  assert.equal(relativeDate(local(2026, 11, 20, 8), local(2026, 11, 28, 23, 59)), '8 days ago');
  assert.equal(relativeDate(local(2026, 11, 29, 8), now), 'Today'); // clock skew never gives a negative age
  assert.equal(daysAgo(local(2026, 3, 1), local(2026, 3, 31)), 30);
  assert.equal(daysAgo(local(2026, 10, 31, 23), local(2026, 11, 1, 1)), 1);
});

test('changelog entries are clamped to two lines and keyboard reachable', () => {
  const css = read('../css/top-bar.css');
  assert.match(css, /\.changelog-summary\s*\{[^}]*-webkit-line-clamp:\s*2/);
  assert.match(css, /\.changelog-top time\s*\{[^}]*text-align:\s*right/);
  const menu = read('../src/components/ChangelogMenu.vue');
  assert.match(menu, /<button type="button" class="changelog-entry"/);
  assert.match(menu, /@keydown\.down/);
  assert.match(menu, /event\.key === 'Escape'/);
  assert.match(menu, /aria-expanded/);
});

test('recent visits are stored per account and as references only', () => {
  const storage = memory();
  recordVisit(storage, 1, 'deck:5');
  recordVisit(storage, 1, 'user:bob');
  recordVisit(storage, 2, 'deck:9');
  assert.deepEqual(readRecents(storage, 1), ['user:bob', 'deck:5']);
  assert.deepEqual(readRecents(storage, 2), ['deck:9']);
  assert.deepEqual(readRecents(storage, null), []);
  clearRecents(storage, 1);
  assert.deepEqual(readRecents(storage, 1), []);
  assert.deepEqual(readRecents(storage, 2), ['deck:9']);
});

test('recent visits dedupe, cap, and reject unsafe or corrupt data', () => {
  const storage = memory();
  for (let n = 0; n < 15; n++) recordVisit(storage, 1, `deck:${n}`);
  recordVisit(storage, 1, 'deck:10');
  const list = readRecents(storage, 1);
  assert.equal(list.length, MAX_RECENT);
  assert.equal(list[0], 'deck:10');
  assert.equal(new Set(list).size, list.length);
  for (const bad of ['', 'deck:abc', 'user:x', "user:a' OR 1", 'shared:short', '../etc', undefined]) recordVisit(storage, 1, bad);
  assert.deepEqual(readRecents(storage, 1), list);
  storage.setItem('queezo:recent-visits:3', '{not json');
  assert.deepEqual(readRecents(storage, 3), []);
  storage.setItem('queezo:recent-visits:4', JSON.stringify(['deck:1', 7, '<script>', 'user:ok_name']));
  assert.deepEqual(readRecents(storage, 4), ['deck:1', 'user:ok_name']);
  const broken = {getItem() { throw new Error('blocked'); }, setItem() { throw new Error('full'); }};
  assert.deepEqual(readRecents(broken, 1), []);
  assert.doesNotThrow(() => recordVisit(broken, 1, 'deck:1'));
});

test('only deck and profile routes are remembered', () => {
  const token = 'a'.repeat(43);
  assert.equal(visitRefForRoute({name:'deck', params:{deckId:'12'}}), 'deck:12');
  assert.equal(visitRefForRoute({name:'deck-page', params:{deckId:'3'}}), 'deck:3');
  assert.equal(visitRefForRoute({name:'shared', params:{token}}), 'shared:' + token);
  assert.equal(visitRefForRoute({name:'public-profile', params:{username:'bob'}}), 'user:bob');
  assert.equal(visitRefForRoute({name:'friend', params:{username:'amy_1'}}), 'user:amy_1');
  for (const name of ['dashboard', 'gwa', 'pomodoro', 'class-schedule', 'search', 'profile', 'study', 'room', 'shared-study']) {
    assert.equal(visitRefForRoute({name, params:{deckId:'1', token}}), null, name);
  }
  assert.equal(visitRefForRoute(null), null);
});

test('search addresses are normalised and bounded', () => {
  assert.equal(normalizeQuery('  hello   world \n'), 'hello world');
  assert.equal(normalizeQuery('x'.repeat(200)).length, 80);
  assert.equal(normalizeQuery(null), '');
  assert.equal(normalizeTab('mine'), 'mine');
  assert.equal(normalizeTab('admin'), 'all');
  assert.equal(normalizePage('0'), 1);
  assert.equal(normalizePage('99999'), 1);
  assert.equal(normalizePage('3'), 3);
  assert.equal(normalizePage('x'), 1);
  assert.equal(searchLocation(' bio  logy '), '/search?q=bio+logy');
  assert.equal(searchLocation('bio', 'users', 2), '/search?q=bio&tab=users&page=2');
  assert.equal(searchLocation('a&b=c#x'), '/search?q=a%26b%3Dc%23x');
  assert.equal(searchRequestPath('bio', 'bogus', '-4'), '/search?q=bio&type=all&page=1');
  assert.equal(recentRequestPath(['deck:1', 'user:bob']), '/search/recent?ref=deck%3A1&ref=user%3Abob');
});

test('the top bar keeps the existing controls and hides in immersive study views', () => {
  const app = read('../src/App.vue');
  for (const id of ['open-friends', 'open-notifications', 'account-dropdown', 'notifications-panel']) assert.ok(app.includes(`id="${id}"`), id);
  assert.match(app, /<GlobalSearch/);
  assert.match(app, /<ChangelogMenu/);
  const css = read('../css/top-bar.css');
  assert.match(css, /\.signed-in\.study-focus \.top-bar\s*\{\s*display:\s*none/);
  assert.match(css, /@media \(max-width: 760px\)[\s\S]*\.search-toggle\s*\{[^}]*display:\s*inline-flex/);
  assert.match(read('../src/main.js'), /page\('\/search'/);
});
