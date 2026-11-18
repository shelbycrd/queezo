import {enhancePage} from './page-tools.js';
import {showNotice} from './popup.js';

export const app = document.querySelector('#app');
export const backIcon = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m14 5-7 7 7 7"/></svg>';
export const escape = value => String(value ?? '').replace(/[&<>"']/g, character => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[character]));

export function notice(message, success = false) {
  showNotice(message, success);
}

export function mount(html, route) {
  if (route && location.hash !== route) return false;
  app.innerHTML = html;
  const parts = (route || '').slice(1).split('/');
  app.classList.toggle('has-subpage-back', ['deck','study','summary','shared'].includes(parts[0]));
  if (route && ['deck','summary','shared'].includes(parts[0])) {
    const target = parts[0] === 'deck' ? (parts.length > 2 ? `#deck/${parts[1]}` : '#decks') : parts[0] === 'summary' ? app.querySelector('a[href^="#deck/"]')?.getAttribute('href') || '#decks' : '#dashboard';
    app.insertAdjacentHTML('afterbegin', `<a class="subpage-back" href="${escape(target)}" aria-label="Go back">${backIcon}</a>`);
  }
  enhancePage(app);
  return true;
}

export async function busy(container, action) {
  if (container.dataset.busy === 'true') return;
  container.dataset.busy = 'true';
  container.setAttribute('aria-busy','true');
  const buttons = [...container.querySelectorAll('button')];
  const previous = buttons.map(button => button.disabled);
  buttons.forEach(button => { button.disabled = true; });
  try { await action(); }
  catch (error) { notice(error.message); }
  finally {
    container.dataset.busy = 'false';
    container.removeAttribute('aria-busy');
    buttons.forEach((button, index) => { button.disabled = previous[index]; });
  }
}

export const plural = (count, word) => `${count} ${word}${count === 1 ? '' : 's'}`;
export const date = value => new Date(value).toLocaleString(undefined, {dateStyle:'medium', timeStyle:'short'});
export const duration = seconds => `${Math.floor(seconds / 60)}m ${seconds % 60}s`;
