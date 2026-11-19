import {authenticatedUser} from './auth-state.js';
import {escape, mount, app, busy, plural} from './ui.js';
import {api} from './api.js';
import {deckTile} from './deck-view.js';
import {chooseStudy} from './study-options.js';
import {highestStreak} from './profile-data.js';
import {soundsEnabled, setSoundsEnabled, playTimerPress} from './audio.js';

export async function accountPage(section, route) {
  if (section === 'profile') {
    const user = authenticatedUser();
    const [decks, activity, connections] = await Promise.all([api('/decks'), api('/dashboard/activity'), api('/friends')]);
    const publicDecks = decks.filter(deck => deck.visibility === 'public').sort((a,b) => b.created_at.localeCompare(a.created_at) || b.id-a.id);
    const best = highestStreak(activity.active_days);
    if (!mount(`<div class="page-heading"><h1>Profile</h1></div>
      <section class="panel profile-card" aria-label="Your profile">
        <div class="profile-avatar" aria-hidden="true">${escape(Array.from(user.display_name.trim())[0] || 'Q')}</div>
        <div class="profile-identity"><h2>${escape(user.display_name)}</h2><p class="profile-username">@${escape(user.username)}</p>
          <dl class="profile-stats"><div><dt>Total Decks</dt><dd>${decks.length}</dd></div><div><dt>Friends</dt><dd data-friend-count>${connections.friends.length}</dd></div><div><dt>Highest Streak</dt><dd>${best}<span> ${best === 1 ? 'day' : 'days'}</span></dd></div></dl>
        </div>
        <div class="profile-actions"><a class="button" href="#decks">Your decks</a><details class="profile-account"><summary>Account details</summary><dl class="profile-details"><dt>UID</dt><dd><span>${escape(user.uid)}</span> <button type="button" class="secondary small flat-button" data-copy="${escape(user.uid)}">Copy UID</button></dd><dt>Email</dt><dd><span>${escape(user.email)}</span> <button type="button" class="secondary small flat-button" data-copy="${escape(user.email)}">Copy email</button></dd></dl></details></div>
      </section>
      <section class="profile-public"><div class="section-heading"><h2>Public Decks</h2><span class="deck-total">${plural(publicDecks.length,'deck')}</span></div>${publicDecks.length ? `<div class="deck-grid">${publicDecks.map(deckTile).join('')}</div>` : '<div class="empty"><h3>No public decks yet.</h3><p class="muted">Choose Public in a deck’s visibility settings to show it here.</p><a class="button secondary" href="#decks">Manage decks</a></div>'}</section>`, route)) return;
    app.querySelectorAll('[data-study]').forEach(button => button.addEventListener('click', () => busy(button.parentElement, () => chooseStudy(button.dataset.study))));
  } else if (section === 'help') {
    mount(`<div class="page-heading"><h1>Help</h1></div><div class="help-grid"><section class="panel"><h2>Flashcards</h2><p>Create a deck, then add a question and answer. Photos and lists are supported on both sides.</p><p>During study, press <kbd>Enter</kbd> to reveal. Use <kbd>1</kbd>, <kbd>2</kbd>, and <kbd>3</kbd> to rate Hard, Normal, or Easy and continue.</p><a href="#decks">Open flashcards</a></section><section class="panel"><h2>GWA Calculator</h2><p>Enter 1–15 courses with units and grades. Subjects are optional. Type 175 for 1.75; Enter moves to the next course.</p><a href="#gwa">Open calculator</a></section><section class="panel"><h2>Pomodoro</h2><p>Press the play icon to begin. Use pause to pause, Reset timer to restart the phase, or Skip to move on without study credit. Each next phase waits for play. Set durations under Timer settings, and add tasks with a pomodoro target.</p><a href="#pomodoro">Open timer</a></section><section class="panel"><h2>Account access</h2><p>Create an account from the login page. Contact your administrator if you need help accessing an existing account.</p></section></div>`, route);
  } else {
    if (!mount(`<div class="page-heading"><h1>Settings</h1></div><section class="panel account-page"><h2>Sound</h2><label class="setting-toggle"><span><strong>Study sounds</strong><small>Card page turns and Pomodoro play/pause keypress sounds.</small></span><input id="button-sounds" type="checkbox" ${soundsEnabled() ? 'checked' : ''}></label><p class="hint">Saved in this browser. Navigation remains silent.</p><button id="preview-sound" type="button" class="secondary small flat-button" ${soundsEnabled() ? '' : 'disabled'}>Preview sound</button></section>`, route)) return;
    app.querySelector('#preview-sound').onclick = () => { void playTimerPress(); };
    app.querySelector('#button-sounds').addEventListener('change', event => { setSoundsEnabled(event.target.checked); app.querySelector('#preview-sound').disabled = !event.target.checked; });
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
