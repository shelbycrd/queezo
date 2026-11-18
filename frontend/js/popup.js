// One shared overlay; messages never take space in a form or page grid.
export function showNotice(message, success = false) {
  const element = document.querySelector('#notice');
  if (!element) return;
  if (element.matches(':popover-open')) element.hidePopover();
  element.hidden = !message;
  if (!message) { element.replaceChildren(); document.body.append(element); return; }
  const dialog = document.querySelector('dialog[open]');
  (dialog || document.body).append(element);
  element.setAttribute('popover', 'manual');
  element.setAttribute('role', success ? 'status' : 'alert');
  element.classList.toggle('success', success);
  const text = document.createElement('span');
  text.textContent = message;
  const close = document.createElement('button');
  close.type = 'button'; close.className = 'secondary flat-button';
  close.setAttribute('aria-label', 'Dismiss message'); close.textContent = '×';
  close.onclick = () => { showNotice(''); };
  element.replaceChildren(text, close);
  element.showPopover?.();
  if (dialog) dialog.addEventListener('close', () => {
    if (element.parentElement === dialog) showNotice('');
  }, {once:true});
}
