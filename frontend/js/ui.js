export const app = document.querySelector('#app');
export const escape = value => String(value ?? '').replace(/[&<>"']/g, character => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[character]));

export function notice(message, success = false) {
  const element = document.querySelector('#notice');
  element.textContent = message;
  element.hidden = !message;
  element.classList.toggle('success', success);
}

export function mount(html, route) {
  if (route && location.hash !== route) return false;
  app.innerHTML = html;
  return true;
}

export async function busy(container, action) {
  if (container.dataset.busy === 'true') return;
  container.dataset.busy = 'true';
  const buttons = [...container.querySelectorAll('button')];
  const previous = buttons.map(button => button.disabled);
  buttons.forEach(button => { button.disabled = true; });
  try { await action(); }
  catch (error) { notice(error.message); }
  finally {
    container.dataset.busy = 'false';
    buttons.forEach((button, index) => { button.disabled = previous[index]; });
  }
}

export const plural = (count, word) => `${count} ${word}${count === 1 ? '' : 's'}`;
export const date = value => new Date(value).toLocaleString(undefined, {dateStyle:'medium', timeStyle:'short'});
export const duration = seconds => `${Math.floor(seconds / 60)}m ${seconds % 60}s`;
