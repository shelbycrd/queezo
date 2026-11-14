// A small plain-text/list format: user HTML is always displayed as text.
export const escapeContent = value => String(value ?? '').replace(/[&<>"']/g, character => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[character]));
export const MAX_IMAGE_BYTES = 1.5 * 1024 * 1024;

export function safeImageUrl(value) {
  if (typeof value !== 'string' || !/^data:image\/(?:png|jpeg|webp);base64,[A-Za-z0-9+/]+={0,2}$/.test(value)) return '';
  const encoded = value.slice(value.indexOf(',') + 1);
  const bytes = encoded.length * 3 / 4 - (encoded.endsWith('==') ? 2 : encoded.endsWith('=') ? 1 : 0);
  return encoded.length % 4 === 0 && bytes <= MAX_IMAGE_BYTES ? value : '';
}

export function renderText(value) {
  const parts = [];
  let group = [];
  let kind = '';
  const flush = () => {
    if (!group.length) return;
    if (kind === 'ul' || kind === 'ol') parts.push(`<${kind}>${group.map(line => `<li>${escapeContent(line)}</li>`).join('')}</${kind}>`);
    else parts.push(`<p>${group.map(escapeContent).join('<br>')}</p>`);
    group = [];
  };
  for (const line of String(value ?? '').split(/\r?\n/)) {
    if (!line.trim()) { flush(); kind = ''; continue; }
    const bullet = line.match(/^\s*[-*]\s+(.+)$/);
    const numbered = line.match(/^\s*\d+[.)]\s+(.+)$/);
    const nextKind = bullet ? 'ul' : numbered ? 'ol' : 'p';
    if (nextKind !== kind) flush();
    kind = nextKind;
    group.push(bullet?.[1] || numbered?.[1] || line);
  }
  flush();
  return parts.join('');
}

export function renderCardContent(text, image, alt = 'Flashcard photo') {
  const source = safeImageUrl(image);
  return `<div class="formatted-content">${renderText(text)}${source ? `<img class="card-photo" src="${source}" alt="${escapeContent(alt)}" loading="lazy">` : ''}</div>`;
}

export function insertList(value, start, end, ordered = false) {
  const first = start === 0 ? 0 : value.lastIndexOf('\n', start - 1) + 1;
  const nextBreak = value.indexOf('\n', end);
  const last = nextBreak < 0 ? value.length : nextBreak;
  const selection = value.slice(first, last).split('\n');
  const formatted = selection.map((line, index) => `${ordered ? `${index + 1}.` : '-'} ${line.replace(/^\s*(?:[-*]|\d+[.)])\s+/, '')}`).join('\n');
  return {value:value.slice(0, first) + formatted + value.slice(last), start:first, end:first + formatted.length};
}

export function studyShortcut(event) {
  if (event.repeat || event.ctrlKey || event.altKey || event.metaKey || event.isComposing) return null;
  if (event.key === 'Enter') return 'reveal';
  return {'1':'hard','2':'normal','3':'easy'}[event.key] || null;
}
