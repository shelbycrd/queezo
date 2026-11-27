// Per-account "recently visited" decks and profiles for the global search box.
// Only opaque references (deck:12, shared:<token>, user:name) are stored in the browser, never titles.
// The server re-checks each one against current visibility before showing it, so a deck that has since
// become private cannot leak its name from local storage, and each account has its own list.
export const MAX_RECENT = 10;
export const VISIT_REF = /^(?:deck:\d{1,12}|shared:[A-Za-z0-9_-]{32,64}|user:[A-Za-z0-9_]{3,32})$/;
const keyFor = userId => `queezo:recent-visits:${userId}`;

// The reference for a route the user opened, or null for pages that are not decks or profiles.
export function visitRefForRoute(route) {
  const params = route?.params ?? {};
  if (['deck', 'deck-page'].includes(route?.name) && params.deckId) return `deck:${params.deckId}`;
  if (route?.name === 'shared' && params.token) return `shared:${params.token}`;
  if (['public-profile', 'friend'].includes(route?.name) && params.username) return `user:${params.username}`;
  return null;
}

function read(storage, userId) {
  try {
    const parsed = JSON.parse(storage.getItem(keyFor(userId)) ?? '[]');
    return Array.isArray(parsed) ? parsed.filter(value => typeof value === 'string' && VISIT_REF.test(value)).slice(0, MAX_RECENT) : [];
  } catch { return []; }
}

export function readRecents(storage, userId) {
  return userId == null ? [] : read(storage, userId);
}

export function recordVisit(storage, userId, ref) {
  if (userId == null || !VISIT_REF.test(ref ?? '')) return readRecents(storage, userId);
  const next = [ref, ...read(storage, userId).filter(value => value !== ref)].slice(0, MAX_RECENT);
  try { storage.setItem(keyFor(userId), JSON.stringify(next)); } catch { /* storage may be unavailable or full */ }
  return next;
}

export function clearRecents(storage, userId) {
  if (userId == null) return;
  try { storage.removeItem(keyFor(userId)); } catch { /* ignore */ }
}

export function browserStorage() {
  try { return globalThis.localStorage ?? null; } catch { return null; }
}
