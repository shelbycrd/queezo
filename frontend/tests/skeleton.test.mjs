import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';

const read = path => readFileSync(new URL('../' + path, import.meta.url), 'utf8');
const skeleton = read('src/components/LoadingSkeleton.vue');
const css = read('css/skeleton.css');

const pageVariants = ['decks', 'deck', 'shared-deck', 'home', 'profile', 'summary', 'study-card', 'schedule', 'results', 'schedule-rows', 'friends', 'track'];

test('every page-specific skeleton variant is rendered', () => {
  for (const name of pageVariants) assert.ok(skeleton.includes("'" + name + "'") || skeleton.includes('"' + name + '"') || skeleton.includes(name), name);
  for (const name of ['decks', 'deck', 'shared-deck', 'home', 'profile', 'summary', 'study-card', 'schedule', 'results', 'schedule-rows'])
    assert.match(skeleton, new RegExp(`variant === '${name}'`), name);
});

test('skeletons reuse the real layout classes so dimensions follow the page', () => {
  for (const cls of ['page-heading', 'deck-grid', 'portrait-deck', 'deck-cover', 'home-dashboard', 'profile-card', 'profile-layout', 'timetable', 'tt-day', 'study-sheet', 'recall-ratings', 'summary-grid', 'saved-card', 'search-result'])
    assert.ok(skeleton.includes(cls) || read('src/components/SkeletonTile.vue').includes(cls), cls);
});

test('skeleton keeps one status wrapper and hides the decorative structure', () => {
  assert.match(skeleton, /role="status" aria-live="polite" aria-busy="true"/);
  assert.match(skeleton, /<span class="sr-only">\{\{ label \}\}<\/span>/);
  assert.match(skeleton, /<div aria-hidden="true" class="sk-root">/);
  assert.equal((skeleton.match(/role="status"/g) || []).length, 1);
});

test('skeleton motion is subtle and disabled for reduced motion', () => {
  assert.match(css, /@keyframes sk-outline/);
  assert.match(css, /@media\(prefers-reduced-motion:reduce\)\{\.skeleton \.sk\{animation:none/);
});

test('consumers request the page-specific variants', () => {
  const uses = {
    'src/views/DecksView.vue': 'variant="decks"',
    'src/views/DeckView.vue': 'variant="deck"',
    'src/views/SharedView.vue': 'variant="shared-deck"',
    'src/views/DashboardView.vue': 'variant="home"',
    'src/views/ProfileView.vue': 'variant="profile"',
    'src/views/StudySummary.vue': 'variant="summary"',
    'src/views/StudyView.vue': 'variant="study-card"',
    'src/views/ScheduleView.vue': 'variant="schedule"',
    'src/views/SearchView.vue': 'variant="results"',
    'src/components/HomeSchedule.vue': 'variant="schedule-rows"',
    'src/components/FriendsDrawer.vue': 'variant="friends"',
  };
  for (const [file, text] of Object.entries(uses)) assert.ok(read(file).includes(text), file);
});

test('deck tile placeholder does not use the pastel cover colours', () => {
  assert.match(css, /\.sk-cover\.deck-cover\{background:#f1f6fd/);
});
