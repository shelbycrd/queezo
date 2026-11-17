import {dashboard, decks} from './decks.js';
import {cardForm, deckPage} from './flashcards.js';
import {studyPage, stopStudyListeners, summaryPage} from './study.js';
import {app, mount, notice} from './ui.js';
import {gwaPage} from './gwa.js';
import {initPomodoro, pomodoroPage, setPomodoroUser, stopPomodoroView} from './pomodoro.js';
import {authenticatedUser} from './auth-state.js';
import {initAuth, loginPage, signupPage, restoreSession} from './auth.js';
import {initButtonFeedback} from './audio.js';
import {accountPage, initAccountMenu} from './account-pages.js';
import {initCommunicationPanels, resetCommunicationPanels} from './chat-preview.js';
import {closeStudyOptions} from './study-options.js';

let authReady = false;

async function navigate() {
  if (!authReady) return;
  stopStudyListeners();
  stopPomodoroView();
  notice('');
  const route = location.hash || '#dashboard';
  const parts = route.slice(1).split('/');
  if (!authenticatedUser()) {
    if (!['#login','#signup'].includes(route)) { location.replace('#login'); return; }
    if (route === '#signup') signupPage(route); else loginPage(route);
    app.focus({preventScroll:true});
    return;
  }
  if (['login','signup'].includes(parts[0])) { location.replace('#dashboard'); return; }
  document.querySelectorAll('[data-nav]').forEach(link => {
    const section = ['deck','study','summary'].includes(parts[0]) ? 'decks' : parts[0];
    if (link.dataset.nav === section) link.setAttribute('aria-current','page');
    else link.removeAttribute('aria-current');
  });
  mount('<p class="muted" role="status">Loading…</p>');
  try {
    if (parts[0] === 'dashboard') await dashboard(location.hash);
    else if (parts[0] === 'decks') await decks(route, parts[1] === 'new');
    else if (parts[0] === 'gwa') gwaPage(route);
    else if (parts[0] === 'pomodoro') pomodoroPage(route);
    else if (['profile','help','settings'].includes(parts[0])) accountPage(parts[0], route);
    else if (parts[0] === 'notes') { location.replace('#gwa'); return; }
    else if (parts[0] === 'deck' && /^\d+$/.test(parts[1])) {
      if (parts[2] === 'add') await cardForm(parts[1], null, route);
      else if (parts[2] === 'edit' && /^\d+$/.test(parts[3])) await cardForm(parts[1], parts[3], route);
      else await deckPage(parts[1], route);
    } else if (parts[0] === 'study' && parts[1]) await studyPage(parts[1], route);
    else if (parts[0] === 'summary' && parts[1]) await summaryPage(parts[1], route);
    else mount('<h1>Page not found</h1><a href="#dashboard">Return to Dashboard</a>', route);
  } catch (error) {
    if ((location.hash || '#dashboard') !== route) return;
    mount('<h1>Couldn’t load this page</h1><p class="muted">Check the message above, or try refreshing the page.</p><a class="button secondary" href="#decks">Return to Flashcards</a>');
    notice(error.message);
  }
  app.focus({preventScroll:true});
}

initButtonFeedback();
initAccountMenu();
initCommunicationPanels();
initPomodoro();
initAuth((previous, user) => {
  resetCommunicationPanels();
  closeStudyOptions();
  stopStudyListeners();
  stopPomodoroView();
  app.innerHTML = '';
  setPomodoroUser(user?.id ?? null);
  if (authReady) {
    const route = user ? '#dashboard' : '#login';
    if (location.hash === route) void navigate();
    else location.replace(route);
  }
});
window.addEventListener('hashchange', navigate);
window.addEventListener('unhandledrejection', event => { notice(event.reason?.message || 'Something went wrong. Please try again.'); });
async function bootstrap() {
  let failure;
  try { await restoreSession(); }
  catch (error) { failure = error; }
  authReady = true;
  await navigate();
  if (failure) notice(failure.message);
}
void bootstrap();
