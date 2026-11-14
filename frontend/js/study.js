import {api} from './api.js';
import {startStudy} from './decks.js';
import {app, duration, escape, mount, notice} from './ui.js';

let cleanup = () => {};
export function stopStudyListeners() { cleanup(); cleanup = () => {}; }

export async function studyPage(sessionId, route) {
  let state = await api(`/study/${sessionId}`);
  if (location.hash !== route) return;
  if (state.status !== 'active') { location.hash = `#summary/${sessionId}`; return; }
  let inFlight = false;
  let showingBack = state.revealed;
  const body = () => ({presentation_number:state.presentation_number, presentation_token:state.presentation_token});

  function render() {
    const card = state.current_card;
    showingBack = state.revealed;
    return mount(`<div class="study-shell"><div class="study-heading"><div><p class="eyebrow">Recall practice</p><h1>${escape(state.deck_title)}</h1></div><button id="exit-study" class="secondary small">Exit Study</button></div>
      <div class="progress-text"><span>${state.completed_cards} of ${state.total_cards} cards completed</span><span>${state.total_reviews} reviews</span></div><progress max="${state.total_cards}" value="${state.completed_cards}" aria-label="Completed flashcards"></progress>
      <button class="flashcard" id="flashcard"><span class="flip-inner ${showingBack ? 'is-flipped' : ''}"><span class="card-face front" aria-hidden="${showingBack}"><span class="label">Question</span><span class="content">${escape(card.front)}</span></span><span class="card-face back" aria-hidden="${!showingBack}"><span class="label">Answer</span><span id="answer" class="content">${escape(card.back || '')}</span></span></span></button>
      <div class="study-tools"><div id="reveal-controls" ${state.revealed ? 'hidden' : ''}><p class="muted">Try recalling the answer before you reveal it.</p><button id="reveal" class="secondary">Reveal answer <span aria-hidden="true">[4]</span></button></div>
      <div id="rating-controls" ${state.revealed ? '' : 'hidden'}><p>How did that feel?</p><div class="ratings"><button class="hard" data-rating="hard">Hard <small>1 · More practice</small></button><button class="normal" data-rating="normal">Normal <small>2 · Getting there</small></button><button class="easy" data-rating="easy">Easy <small>3 · Feeling confident</small></button></div></div></div>
      <p class="shortcut-hint">1 Hard · 2 Normal · 3 Easy · 4 Reveal / flip<br>Card reviewed ${card.review_count} times${card.review_count ? ` · Current target: ${card.target_reviews}` : ''}</p></div>`, route);
  }

  function setDisabled(disabled) { app.querySelectorAll('button').forEach(button => { button.disabled = disabled; }); }

  async function revealOrFlip() {
    if (inFlight) return;
    if (state.revealed) {
      showingBack = !showingBack;
      app.querySelector('.flip-inner').classList.toggle('is-flipped', showingBack);
      app.querySelector('.front').setAttribute('aria-hidden', String(showingBack));
      app.querySelector('.back').setAttribute('aria-hidden', String(!showingBack));
      return;
    }
    inFlight = true; setDisabled(true);
    try {
      const next = await api(`/study/${sessionId}/reveal`, {method:'POST', body:body()});
      if (location.hash !== route) return;
      state = next;
      app.querySelector('#answer').textContent = state.current_card.back;
      app.querySelector('.flip-inner').classList.add('is-flipped');
      app.querySelector('.front').setAttribute('aria-hidden','true');
      app.querySelector('.back').setAttribute('aria-hidden','false');
      showingBack = true;
      app.querySelector('#reveal-controls').hidden = true;
      app.querySelector('#rating-controls').hidden = false;
    } catch (error) { notice(error.message); }
    finally { inFlight = false; if (location.hash === route) setDisabled(false); }
  }

  async function rate(difficulty) {
    if (inFlight || !state.revealed) return;
    inFlight = true; setDisabled(true);
    try {
      const next = await api(`/study/${sessionId}/rate`, {method:'POST', body:{...body(), difficulty}});
      if (location.hash !== route) return;
      state = next;
      notice('');
      if (state.status === 'completed') location.hash = `#summary/${sessionId}`;
      else render();
    } catch (error) {
      notice(error.message);
      // A response can be lost AFTER committing. Read the authoritative state
      // so retries cannot strand the UI on an already-consumed presentation.
      try {
        const fresh = await api(`/study/${sessionId}`);
        if (location.hash === route) {
          state = fresh;
          if (state.status !== 'active') location.hash = `#summary/${sessionId}`;
          else render();
        }
      } catch { /* Keep the first actionable error visible. */ }
    } finally { inFlight = false; if (location.hash === route) setDisabled(false); }
  }

  async function onClick(event) {
    const button = event.target.closest('button');
    if (!button || inFlight) return;
    if (button.id === 'flashcard' || button.id === 'reveal') await revealOrFlip();
    else if (button.dataset.rating) await rate(button.dataset.rating);
    else if (button.id === 'exit-study') {
      inFlight = true; setDisabled(true);
      try { await api(`/study/${sessionId}/exit`, {method:'POST'}); location.hash = `#deck/${state.deck_id}`; }
      catch (error) { notice(error.message); }
      finally { inFlight = false; if (location.hash === route) setDisabled(false); }
    }
  }
  function onKey(event) {
    if (event.repeat || event.ctrlKey || event.altKey || event.metaKey || event.target.closest('input,textarea,select,[contenteditable]')) return;
    if (!['1','2','3','4'].includes(event.key)) return;
    event.preventDefault();
    if (event.key === '4') revealOrFlip();
    else rate({'1':'hard','2':'normal','3':'easy'}[event.key]);
  }
  if (!render()) return;
  app.addEventListener('click', onClick);
  document.addEventListener('keydown', onKey);
  cleanup = () => { app.removeEventListener('click', onClick); document.removeEventListener('keydown', onKey); };
}

export async function summaryPage(sessionId, route) {
  const summary = await api(`/study/${sessionId}/summary`);
  if (!mount(`<div class="study-shell"><div class="summary-heading"><div class="check" aria-hidden="true">✓</div><p class="eyebrow">${escape(summary.deck_title)}</p><h1>${summary.status === 'completed' ? 'Study Session Completed!' : 'Study session ended'}</h1><p class="muted">${summary.status === 'completed' ? 'Every card has finished its required reviews. Nice work showing up.' : 'Your progress is saved in the session history.'}</p></div>
    <div class="summary-grid">${[['Unique cards studied',summary.total_unique_cards],['Total appearances',summary.total_reviews],['Session duration',duration(summary.duration_seconds)],['Easy ratings',summary.easy_count],['Normal ratings',summary.normal_count],['Hard ratings',summary.hard_count]].map(([label,value]) => `<div class="stat"><p class="muted">${label}</p><div class="value">${value}</div></div>`).join('')}</div>
    <div class="actions summary-actions"><a class="button secondary" href="#deck/${summary.deck_id}">Return to Deck</a><button id="study-again">Study Again →</button></div></div>`, route)) return;
  app.querySelector('#study-again').addEventListener('click', async event => {
    event.currentTarget.disabled = true;
    try { await startStudy(summary.deck_id); }
    catch (error) { notice(error.message); app.querySelector('#study-again').disabled = false; }
  });
}
