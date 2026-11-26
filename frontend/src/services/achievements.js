// Display helpers for profile achievements. The server decides what each viewer may see.

export function achievementProgress(item) {
  if (item.unlocked || !Number.isFinite(item.goal) || item.goal <= 0) return null;
  const value = Math.max(0, Math.min(item.progress ?? 0, item.goal));
  return {value, goal:item.goal, percent:Math.round(100 * value / item.goal),
    label:value + ' of ' + item.goal + (item.scope === 'daily' ? ' today' : '')};
}

export function unlockedDate(item) {
  if (!item.unlocked_at) return '';
  const date = new Date(item.unlocked_at);
  return Number.isNaN(date.getTime()) ? '' : date.toLocaleDateString(undefined,{month:'long',day:'numeric',year:'numeric'});
}

// Unlocked first, then catalog order (the server returns catalog order).
export function sortedAchievements(items) {
  return [...(items ?? [])].map((item,index) => ({item,index}))
    .sort((a,b) => Number(b.item.unlocked) - Number(a.item.unlocked) || a.index - b.index)
    .map(entry => entry.item);
}
