import {authenticatedUser} from './auth-state.js';
import {escape, mount, app} from './ui.js';
import {soundsEnabled, setSoundsEnabled} from './audio.js';

export function accountPage(section, route) {
  if (section === 'profile') {
    const user = authenticatedUser();
    mount(`<div class="page-heading"><h1>Profile</h1></div><section class="panel account-page"><h2>Your account</h2><dl class="profile-details"><dt>Email</dt><dd>${escape(user.email)}</dd></dl><p class="muted">Your decks and study history belong to this account.</p><a class="button secondary" href="#decks">View your decks</a></section>`, route);
  } else if (section === 'help') {
    mount(`<div class="page-heading"><h1>Help</h1></div><div class="help-grid"><section class="panel"><h2>Flashcards</h2><p>Create a deck, then add a question and answer. Photos and lists are supported on both sides.</p><p>During study, press <kbd>Enter</kbd> to reveal. Use <kbd>1</kbd>, <kbd>2</kbd>, and <kbd>3</kbd> to rate Hard, Normal, or Easy and continue.</p><a href="#decks">Open flashcards</a></section><section class="panel"><h2>GWA Calculator</h2><p>Enter 1–15 courses with units and grades. Subjects are optional. Type 175 for 1.75; Enter moves to the next course.</p><a href="#gwa">Open calculator</a></section><section class="panel"><h2>Pomodoro</h2><p>Press Start to begin. After each phase, use the timer’s main button to start the next study or break when you’re ready. Set durations under Timer settings, and add tasks with a pomodoro target.</p><a href="#pomodoro">Open timer</a></section><section class="panel"><h2>Account access</h2><p>Accounts are provided by your administrator. Contact them if you need help accessing your account.</p></section></div>`, route);
  } else {
    if (!mount(`<div class="page-heading"><h1>Settings</h1></div><section class="panel account-page"><h2>Sound</h2><label class="setting-toggle"><span><strong>Card page-turn sound</strong><small>Play a page-turn sound when saving the next card.</small></span><input id="button-sounds" type="checkbox" ${soundsEnabled() ? 'checked' : ''}></label><p class="hint">Saved in this browser. Navigation and button clicks are silent.</p></section>`, route)) return;
    app.querySelector('#button-sounds').addEventListener('change', event => setSoundsEnabled(event.target.checked));
  }
}

export function initAccountMenu() {
  const dropdown = document.querySelector('#account-dropdown');
  document.addEventListener('click', event => {
    if (!dropdown.contains(event.target) || event.target.closest('.account-menu a,.account-menu button')) dropdown.open = false;
  });
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape' && dropdown.open) {
      dropdown.open = false;
      dropdown.querySelector('summary').focus();
    }
  });
  window.addEventListener('hashchange', () => { dropdown.open = false; });
}
