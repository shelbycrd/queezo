// Calendar-day keys come from the account-private activity endpoint (Asia/Manila).
export function highestStreak(activeDays) {
  const days = [...new Set(activeDays)].sort();
  let best = 0, run = 0, previous;
  for (const day of days) {
    const value = Date.parse(`${day}T00:00:00Z`);
    if (!Number.isFinite(value)) continue;
    run = value - previous === 86400000 ? run + 1 : 1;
    best = Math.max(best, run);
    previous = value;
  }
  return best;
}
