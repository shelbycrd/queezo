import {api} from './api.js';
import {startStudy} from './decks.js';
import {app, backIcon, duration, escape, mount, notice, plural} from './ui.js';
import {renderCardContent, studyShortcut} from './card-content.js';
import {loadTiming, saveTiming} from './study-options.js';

let cleanup = () => {};
export function stopStudyListeners() { cleanup(); cleanup = () => {}; }

export async function studyPage(sessionId, route) {
  let alive = true;
  cleanup = () => { alive = false; };
  let state = await api(`/study/${sessionId}`);
  const active = () => alive && location.hash === route;
  if (!active()) return;
  if (state.status !== 'active') { location.hash = `#summary/${sessionId}`; return; }
  let inFlight = false;
  const timing = loadTiming(sessionId);
  let interval;
  let ending = false;
  const body = () => ({presentation_number:state.presentation_number, presentation_token:state.presentation_token});

  function render() {
    if (timing.mode === 'timed' && (!timing.deadline || (timing.scope === 'question' && timing.presentation !== state.presentation_number))) {
      timing.deadline = Date.now() + timing.seconds * 1000;
      timing.presentation = state.presentation_number;
      delete timing.expiredPresentation;
      saveTiming(sessionId, timing);
    }
    const secondsLeft = Math.max(0, Math.ceil(((timing.deadline || 0) - Date.now()) / 1000));
    const timeText = `${String(Math.floor(secondsLeft / 60)).padStart(2,'0')}:${String(secondsLeft % 60).padStart(2,'0')}`;
    const card = state.current_card;
    return mount(`<div class="study-shell"><div class="study-heading"><button id="exit-study" class="secondary small flat-button" aria-label="Back to deck">${backIcon}</button><div><p class="eyebrow">A little focused recall</p><h1>${escape(state.deck_title)}</h1></div></div>
      ${timing.mode === 'timed' ? `<div class="study-clock"><span>${timing.scope === 'question' ? 'Time for this question' : 'Time for this deck'}</span><strong id="study-time-left" role="timer">${timeText}</strong><span id="study-time-message"></span></div>` : ''}
      <div class="progress-text"><span>${state.completed_cards} of ${state.total_cards} cards complete</span><span>${plural(state.total_reviews,'review')}</span></div><progress max="${state.total_cards}" value="${state.completed_cards}" aria-label="Completed flashcards"></progress>
      <article class="study-sheet ${state.revealed ? 'answer-revealed' : ''}" aria-label="Flashcard"><section class="study-question" tabindex="-1"><span class="content-label">Question</span>${renderCardContent(card.front, card.front_image, 'Question photo')}</section>
        ${state.revealed ? `<section class="study-answer" id="answer" aria-label="Revealed answer"><span class="content-label">Answer</span>${renderCardContent(card.back, card.back_image, 'Answer photo')}</section>` : `<div class="study-reveal-prompt"><button id="reveal" type="button" class="secondary">Reveal answer <kbd>Enter</kbd></button><p>Press Enter to reveal</p></div>`}
      </article>
      <div class="study-actions"><p class="muted">${state.revealed ? 'How well did you remember?' : 'Know it already? Rate your recall to reveal and continue.'}</p><div class="ratings recall-ratings"><button class="hard" data-rating="hard"><kbd>1</kbd><span>Hard</span><small>More practice</small></button><button class="normal" data-rating="normal"><kbd>2</kbd><span>Normal</span><small>Getting there</small></button><button class="easy" data-rating="easy"><kbd>3</kbd><span>Easy</span><small>Feeling confident</small></button></div></div>
      <p class="shortcut-hint">${plural(card.review_count,'review')} of this card${card.review_count ? ` · Current target: ${card.target_reviews}` : ''}</p></div>`, route);
  }

  function setDisabled(disabled) {
    if (!active()) return;
    app.querySelectorAll('.study-shell button').forEach(button => { button.disabled = disabled; });
  }

  async function recover(error) {
    if (!active()) return;
    notice(error.message);
    // Lost responses can occur after a successful server commit. Recover the
    // authoritative presentation instead of retrying an already-consumed token.
    try {
      const fresh = await api(`/study/${sessionId}`);
      if (!active()) return;
      state = fresh;
      if (state.status !== 'active') location.hash = `#summary/${sessionId}`;
      else render();
    } catch { /* Keep the original actionable error visible. */ }
  }

  async function reveal() {
    if (!active() || inFlight || state.revealed) return;
    inFlight = true; setDisabled(true);
    try {
      const fresh = await api(`/study/${sessionId}/reveal`, {method:'POST', body:body()});
      if (!active()) return;
      state = fresh;
      render();
      // Direct rendering: the question stays visible, with its answer below.
      app.querySelector('.study-question')?.focus({preventScroll:true});
    } catch (error) { await recover(error); }
    finally { inFlight = false; setDisabled(false); }
  }

  async function rate(difficulty) {
    if (!active() || inFlight) return;
    inFlight = true; setDisabled(true);
    try {
      if (!state.revealed) {
        const revealed = await api(`/study/${sessionId}/reveal`, {method:'POST', body:body()});
        if (!active()) return;
        state = revealed;
        render();
        setDisabled(true);
      }
      const fresh = await api(`/study/${sessionId}/rate`, {method:'POST', body:{...body(), difficulty}});
      if (!active()) return;
      state = fresh;
      notice('');
      if (state.status !== 'active') location.hash = `#summary/${sessionId}`;
      else { render(); app.querySelector('.study-question')?.focus({preventScroll:true}); }
    } catch (error) { await recover(error); }
    finally { inFlight = false; setDisabled(false); }
  }

  function tick() {
    if (!active() || timing.mode !== 'timed') return;
    const remaining = Math.max(0, Math.ceil((timing.deadline - Date.now()) / 1000));
    const display = app.querySelector('#study-time-left');
    if (display) display.textContent = `${String(Math.floor(remaining / 60)).padStart(2,'0')}:${String(remaining % 60).padStart(2,'0')}`;
    if (remaining || inFlight || ending) return;
    if (timing.scope === 'question') {
      const message = app.querySelector('#study-time-message');
      if (message) message.textContent = 'Time is up. Review the answer and rate your recall.';
      if (timing.expiredPresentation !== state.presentation_number) {
        timing.expiredPresentation = state.presentation_number;
        saveTiming(sessionId, timing);
        void reveal();
      }
    } else {
      ending = true; inFlight = true; setDisabled(true);
      void api(`/study/${sessionId}/exit`, {method:'POST'}).then(() => {
        if (active()) location.hash = `#summary/${sessionId}`;
      }).catch(error => {
        if (active()) { notice(`${error.message} Use Back to deck to end the session.`); inFlight = false; const exit = app.querySelector('#exit-study'); if (exit) exit.disabled = false; }
      });
    }
  }

  async function onClick(event) {
    const button = event.target.closest('button');
    if (!button || inFlight || !active()) return;
    if (button.id === 'reveal') await reveal();
    else if (button.dataset.rating) await rate(button.dataset.rating);
    else if (button.id === 'exit-study') {
      inFlight = true; setDisabled(true);
      try {
        await api(`/study/${sessionId}/exit`, {method:'POST'});
        if (active()) location.hash = `#deck/${state.deck_id}`;
      } catch (error) { if (active()) notice(error.message); }
      finally { inFlight = false; setDisabled(false); }
    }
  }
  function onKey(event) {
    if (!active() || event.target.closest('input,textarea,select,[contenteditable]')) return;
    const action = studyShortcut(event);
    if (!action || event.target.closest('dialog,#account-controls,#main-navigation,.sidebar-settings') || (action === 'reveal' && event.target.closest('#exit-study'))) return;
    event.preventDefault();
    if (action === 'reveal') void reveal();
    else void rate(action);
  }
  if (!render()) return;
  tick();
  if (timing.mode === 'timed') interval = setInterval(tick, 250);
  app.addEventListener('click', onClick);
  document.addEventListener('keydown', onKey);
  cleanup = () => { alive = false; clearInterval(interval); app.removeEventListener('click', onClick); document.removeEventListener('keydown', onKey); };
}

export async function summaryPage(sessionId, route) {
  const summary = await api(`/study/${sessionId}/summary`);
  const timing = loadTiming(sessionId);
  if (!mount(`<div class="study-shell"><div class="summary-heading"><div class="check" aria-hidden="true">✓</div><p class="eyebrow">${escape(summary.deck_title)}</p><h1>${summary.status === 'completed' ? 'Study session complete' : 'Study session ended'}</h1><p class="muted">${summary.status === 'completed' ? 'Every card has finished its reviews. A little more knowledge, a little more confidence.' : 'Your progress is saved in your session history.'}</p></div>
    ${summary.status !== 'completed' && timing.scope === 'deck' && timing.deadline <= Date.now() ? '<p class="timed-session-ended">Your deck time limit was reached.</p>' : ''}
    <div class="summary-grid">${[['Cards studied',summary.total_unique_cards],['Total reviews',summary.total_reviews],['Time together',duration(summary.duration_seconds)],['Easy ratings',summary.easy_count],['Normal ratings',summary.normal_count],['Hard ratings',summary.hard_count]].map(([label,value]) => `<div class="stat"><p class="muted">${label}</p><div class="value">${value}</div></div>`).join('')}</div>
    <div class="actions summary-actions"><a class="button secondary" href="#deck/${summary.deck_id}">Return to deck</a><button id="study-again">Study again →</button></div></div>`, route)) return;
  const button = app.querySelector('#study-again');
  button.addEventListener('click', async () => {
    button.disabled = true;
    try { await startStudy(summary.deck_id); }
    catch (error) { if (button.isConnected) { notice(error.message); button.disabled = false; } }
    finally { if (button.isConnected) button.disabled = false; }
  });
}
