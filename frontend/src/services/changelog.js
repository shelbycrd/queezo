export const CHANGELOG_LIMIT = 4;

const dayStart = value => new Date(value.getFullYear(), value.getMonth(), value.getDate());

// Whole calendar days between two instants in the viewer's local time zone (DST-safe, unlike dividing milliseconds).
export function daysAgo(value, now = new Date()) {
  const a = dayStart(now), b = dayStart(new Date(value));
  return Math.round((Date.UTC(a.getFullYear(), a.getMonth(), a.getDate()) - Date.UTC(b.getFullYear(), b.getMonth(), b.getDate())) / 86400000);
}

export function relativeDate(value, now = new Date()) {
  const days = daysAgo(value, now);
  if (days <= 0) return 'Today';
  if (days === 1) return 'Yesterday';
  if (days < 30) return `${days} days ago`;
  return new Date(value).toLocaleDateString(undefined, {dateStyle:'medium'});
}

// Newest first, bounded, ignoring malformed or future-dated entries.
export function latestReleases(list, now = new Date(), limit = CHANGELOG_LIMIT) {
  return list
    .filter(item => item?.title && item.summary && !Number.isNaN(new Date(item.date).getTime()) && new Date(item.date) <= now)
    .sort((a, b) => new Date(b.date) - new Date(a.date))
    .slice(0, limit)
    .map(item => ({...item, when:relativeDate(item.date, now)}));
}
