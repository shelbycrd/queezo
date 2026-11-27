// Home dashboard helpers.

// Greeting by the browser's local clock: morning 05:00–11:59, afternoon 12:00–17:59, evening otherwise.
export function greeting(now = new Date()) {
  const hour = now.getHours();
  if (hour >= 5 && hour < 12) return 'Good morning';
  if (hour >= 12 && hour < 18) return 'Good afternoon';
  return 'Good evening';
}

// Online friends first, then by display name.
export function sortFriends(friends = []) {
  return [...friends].sort((a, b) => Number(Boolean(b.online)) - Number(Boolean(a.online))
    || String(a.display_name || a.username).localeCompare(String(b.display_name || b.username)));
}
