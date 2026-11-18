import {showNotice} from './popup.js';
// Small, page-local controls. No account data or clipboard contents are read.
export function enhancePage(root) {
  root.querySelectorAll('input[type=password]').forEach(input => {
    const wrapper = document.createElement('div');
    wrapper.className = 'password-control';
    input.before(wrapper); wrapper.append(input);
    const button = document.createElement('button');
    button.type = 'button'; button.className = 'secondary small flat-button';
    button.textContent = 'Show'; button.setAttribute('aria-label', `Show ${input.labels?.[0]?.textContent || 'password'}`);
    button.setAttribute('aria-controls',input.id); button.setAttribute('aria-pressed','false');
    button.onclick = () => {
      const reveal = input.type === 'password';
      input.type = reveal ? 'text' : 'password'; button.textContent = reveal ? 'Hide' : 'Show';
      button.setAttribute('aria-pressed',String(reveal));
      button.setAttribute('aria-label',`${reveal ? 'Hide' : 'Show'} ${input.labels?.[0]?.textContent || 'password'}`);
    };
    wrapper.append(button);
  });
  root.querySelectorAll('[data-copy]').forEach(button => {
    button.onclick = async () => {
      button.disabled=true;
      try { await navigator.clipboard.writeText(button.dataset.copy); showNotice('Copied ✓', true); }
      catch { showNotice('Copy unavailable. Select the value and copy it manually.'); }
      finally { button.disabled=false; }
    };
  });
}
