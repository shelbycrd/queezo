export const plural = (count, word) => `${count} ${word}${count === 1 ? '' : 's'}`;
export const date = value => new Date(value).toLocaleString(undefined, {dateStyle:'medium', timeStyle:'short'});
export const duration = seconds => `${Math.floor(seconds / 60)}m ${seconds % 60}s`;
export const closeIcon = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="m6 6 12 12M18 6 6 18"/></svg>';
export const backIcon = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m14 5-7 7 7 7"/></svg>';
