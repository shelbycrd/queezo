import {api} from './api.js';
import {authVersion} from './auth-state.js';
import {renderCardContent, safeImageUrl} from './card-content.js';
import {multipleChoiceSession, scoreSummary, SESSION_LABELS} from './multiple-choice-session.js';
import {chooseStudy} from './study-options.js';
import {app, backIcon, date, escape, mount, plural} from './ui.js';

const FAILURE_LABELS = {
  generation_failed:'Could not find three distinct choices. Check Ollama or add cards with different answers.',
  insufficient_distractors:'Too few distinct answers for this card. Add cards with different answers or retry with Ollama.',
  ollama_unavailable:'Ollama is unavailable. Check that it is running and the model is installed, then retry.',
  generation_timeout:'Ollama took too long to respond. Retry the failed cards.',
  invalid_ai_response:'Ollama returned an unreadable response. Retry or add cards with different answers.',
  card_missing:'The card was deleted or is no longer accessible.',
  card_changed:'The card changed during preparation.',
  preparation_timeout:'Preparation ran out of time.',
  interrupted:'Preparation was interrupted.',
  preparation_failed:'Could not prepare this card.',
};

const button = (action, label, secondary = false, disabled = false) =>
  `<button type="button" data-mc-action="${action}" ${secondary ? 'class="secondary flat-button"' : ''} ${disabled ? 'disabled' : ''}>${label}</button>`;

const deckLink = session => session
  ? `<a class="button secondary flat-button" href="#deck/${escape(session.deck_id)}">Return to deck</a>`
  : '<a class="button secondary flat-button" href="#decks">Return to Flashcards</a>';

function preparationView(session, pending) {
  const {progress, status} = session;
  const failed = status === 'failed';
  const heading = failed
    ? (progress.ready ? 'Some questions couldn’t be prepared' : 'Questions couldn’t be prepared')
    : 'Preparing your questions';
  const explanation = failed
    ? (progress.ready ? 'Retry failed cards, study the ready questions, or return to your deck.' :
      'Retry the failed cards or return to your deck to use Classic Mode.')
    : 'Queezo reuses saved choices and generates missing ones locally with Ollama.';
  return `<section class="panel mc-panel" aria-labelledby="mc-state-heading">
    <h2 id="mc-state-heading" data-mc-focus tabindex="-1">${heading}</h2>
    <p class="muted">${explanation}</p>
    <div class="mc-preparation-progress" role="status">
      <div class="progress-text"><strong>${progress.completed} of ${progress.total} prepared or checked</strong><span>${progress.ready} ready · ${progress.failed} failed</span></div>
      <progress max="${progress.total}" value="${progress.completed}" aria-label="Question preparation progress"></progress>
    </div>
    ${session.failures.length ? `<details class="mc-failures"><summary>See failed cards (${session.failures.length})</summary>
      <ul>${session.failures.map(item => `<li><strong>Card ID ${escape(item.card_id)}</strong><span>${escape(FAILURE_LABELS[item.reason] || 'Could not prepare this card.')}</span></li>`).join('')}</ul></details>` : ''}
    <div class="actions mc-actions">
      ${failed ? button('retry', pending === 'retry' ? 'Retrying…' : 'Retry failed cards', false, pending) : ''}
      ${failed && progress.ready ? button('continue', pending === 'continue' ? 'Opening…' : `Study ${plural(progress.ready,'ready question')}`, true, pending) : ''}
      ${button('cancel', pending === 'cancel' ? 'Cancelling…' : 'Cancel preparation', true, pending)}
    </div></section>`;
}

function questionView(session, question, grade, pending, selection) {
  const ready = session.progress.ready;
  const completed = session.answered;
  const ordinal = grade ? completed : completed + 1;
  const options = question.options.map((option, index) => {
    const text = `<span class="mc-letter" aria-hidden="true">${String.fromCharCode(65 + index)}</span><span class="mc-option-text">${escape(option.text)}</span>`;
    if (!grade) return `<label class="mc-option"><input name="answer" type="radio" required value="${escape(option.id)}" ${selection === option.id ? 'checked' : ''}>${text}</label>`;
    const correct = option.id === grade.correct_option.id;
    const chosen = option.id === grade.selected_option_id;
    const mark = correct && chosen ? 'Correct answer · Your choice' : correct ? 'Correct answer' : chosen ? 'Your choice' : '';
    const image = correct ? safeImageUrl(grade.back_image) : '';
    return `<li class="mc-option ${correct ? 'mc-correct' : chosen ? 'mc-incorrect' : ''}">${text}
      ${mark ? `<span class="mc-option-mark">${mark}</span>` : ''}
      ${image ? `<div class="mc-option-photo"><img class="card-photo" src="${image}" alt="Answer photo"></div>` : ''}</li>`;
  }).join('');
  return `<div class="progress-text"><strong>Question ${ordinal} of ${ready}</strong><span>${completed} answered</span></div>
    <progress max="${ready}" value="${completed}" aria-label="Questions answered"></progress>
    <article class="study-sheet mc-question"><section class="study-question">
      <h2 class="content-label" data-mc-focus tabindex="-1">Question ${ordinal}</h2>
      ${renderCardContent(question.front, question.front_image, 'Question photo')}
    </section></article>
    ${grade ? `<ul class="mc-options mc-graded-options" data-mc-feedback tabindex="-1" aria-label="${grade.is_correct ? 'Correct. Answer choices' : 'Incorrect. Answer choices'}">${options}</ul>
      <div class="actions mc-actions">${button('next', pending === 'next' ? 'Loading…' : session.status === 'completed' ? 'See results' : 'Next question', false, pending)}${session.status === 'active' ? button('cancel', 'End session', true, pending) : ''}</div>`
    : `<form id="mc-answer-form"><fieldset class="mc-choices" ${pending ? 'disabled' : ''}>
      <legend>Choose one answer</legend><div class="mc-options">${options}</div></fieldset>
      <div class="actions mc-actions"><button type="submit" ${pending ? 'disabled' : ''}>${pending === 'answer' ? 'Checking…' : 'Check answer'}</button>${button('cancel', pending === 'cancel' ? 'Ending…' : 'End session', true, pending)}</div></form>`}`;
}

function summaryView(session, choosing) {
  const score = scoreSummary(session);
  const stats = [['Correct',score.correct],['Incorrect',score.incorrect],['Questions',score.total],
    ['Accuracy',score.accuracy === null ? '—' : `${score.accuracy}%`]];
  return `<div class="summary-heading"><div class="check" aria-hidden="true">✓</div>
    <h2 data-mc-focus tabindex="-1">Session complete</h2>${session.progress.failed ? `<p class="muted">${plural(session.progress.failed,'card')} skipped during preparation.</p>` : ''}</div>
    <div class="summary-grid mc-summary-grid">${stats.map(([label,value]) => `<div class="stat"><p class="muted">${label}</p><div class="value">${value}</div></div>`).join('')}</div>
    <div class="actions mc-actions">${button('again','Study again',false,choosing)}${deckLink(session)}</div>`;
}

function endedView(session) {
  const expired = session.status === 'expired';
  return `<section class="panel mc-panel"><h2 data-mc-focus tabindex="-1">${expired ? 'Session expired' : 'Session cancelled'}</h2>
    <p class="muted">${expired ? 'Multiple-Choice sessions expire after 24 hours.' : 'This session has ended.'} You can start a new session from your deck.</p>
    <div class="actions mc-actions">${deckLink(session)}</div></section>`;
}

function problemView(view) {
  const {status, message} = view.problem;
  const unavailable = status === 404 || status === 401;
  return `<section class="panel mc-panel">
    <h2 data-mc-focus tabindex="-1">${unavailable ? 'Session unavailable' : 'Couldn’t load study progress'}</h2>
    <p role="alert" class="muted">${escape(message)}</p>
    ${!unavailable ? '<p class="muted">Reconnect to load the latest saved progress before continuing.</p>' : ''}
    <div class="actions mc-actions">${!unavailable ? button('refresh','Try again') : ''}${deckLink(view.session)}</div>
  </section>`;
}

let stop = () => {};
export function stopMultipleChoice() { stop(); stop = () => {}; }

export async function multipleChoicePage(sessionId, route) {
  const accountVersion = authVersion();
  let alive = true;
  let lastPhase;
  let lastQuestionId;
  let selection;
  let choosing = false;
  let previousView;
  const active = () => alive && location.hash === route && authVersion() === accountVersion;

  async function newSession() {
    if (choosing) return;
    choosing = true;
    render(previousView);
    try { await chooseStudy(previousView.session.deck_id, {mode:'multiple-choice'}); }
    finally {
      choosing = false;
      if (active()) render(previousView);
    }
  }

  function render(view) {
    if (!active()) return;
    previousView = view;
    const {session, question, grade, problem, pending, message} = view;
    const questionId = problem ? lastQuestionId : question?.id;
    if (lastQuestionId !== questionId) selection = undefined;
    lastQuestionId = questionId;
    const focusedAction = document.activeElement?.dataset.mcAction;
    let content;
    let phase;
    if (problem) { phase = 'problem'; content = problemView(view); }
    else if (grade || (session?.status === 'active' && question)) {
      phase = grade ? `feedback:${question.id}` : `question:${question.id}`;
      content = questionView(session, question, grade, pending, selection);
    } else if (session?.status === 'completed') {
      phase = 'completed'; content = summaryView(session, choosing);
    } else if (session && ['expired','cancelled'].includes(session.status)) {
      phase = session.status; content = endedView(session);
    } else if (session && ['preparing','failed'].includes(session.status)) {
      phase = session.status; content = preparationView(session, pending);
    } else {
      phase = 'loading'; content = '<p class="muted" role="status">Loading study session…</p>';
    }
    const failuresOpen = app.querySelector('.mc-failures')?.open;
    if (!mount(`<div class="study-shell mc-shell">
      <div class="study-heading"><a class="button secondary small flat-button mc-back" href="${session ? `#deck/${escape(session.deck_id)}` : '#decks'}" aria-label="Back to deck">${backIcon}</a>
      <div><p class="eyebrow">Multiple-Choice Mode</p><h1>${escape(session?.deck_title || 'Multiple-Choice Study')}</h1></div></div>
      ${message ? `<p role="status" class="mc-note">${escape(message)}</p>` : ''}
      <div class="mc-content" aria-busy="${Boolean(pending)}">${content}</div></div>`, route)) return;
    const shell = app.querySelector('.mc-shell');
    const failures = shell.querySelector('.mc-failures');
    if (failures && failuresOpen) failures.open = true;
    shell.addEventListener('click', event => {
      const action = event.target.closest('[data-mc-action]')?.dataset.mcAction;
      if (action === 'refresh') void controller.refresh();
      else if (action === 'next') void controller.next();
      else if (action === 'again') void newSession();
      else if (action) void controller.transition(action);
    });
    const form = shell.querySelector('#mc-answer-form');
    form?.addEventListener('change', event => { selection = event.target.value; });
    form?.addEventListener('submit', event => {
      event.preventDefault();
      const option = form.querySelector('input:checked');
      if (option) void controller.answer(option.value);
    });
    if (phase !== lastPhase) {
      shell.querySelector(grade && !problem ? '[data-mc-feedback]' : '[data-mc-focus]')?.focus();
    } else if (focusedAction) {
      [...shell.querySelectorAll('[data-mc-action]')].find(element =>
        element.dataset.mcAction === focusedAction && !element.disabled)?.focus({preventScroll:true});
    }
    lastPhase = phase;
  }

  const controller = multipleChoiceSession(sessionId, {update:render, active});
  stop = () => { alive = false; controller.stop(); };
  await controller.refresh();
}

export function setupMultipleChoiceHistory(details, deckId, route) {
  let loading = false;
  let loaded = false;
  const list = details.querySelector('[data-mc-history]');
  const version = authVersion();
  const active = () => details.isConnected && location.hash === route && authVersion() === version;

  async function load() {
    if (!active() || loading || loaded) return;
    loading = true;
    list.textContent = 'Loading Multiple-Choice history…';
    try {
      const sessions = await api(`/decks/${deckId}/multiple-choice/sessions`);
      if (!active()) return;
      loaded = true;
      details.querySelector('[data-mc-history-count]').textContent = `(${sessions.length})`;
      list.innerHTML = sessions.length ? `<div class="panel"><ul class="history-list">${sessions.map(session => `<li><div>
        <p>${escape(date(session.created_at))} · <strong>${escape(SESSION_LABELS[session.status] || session.status)}</strong></p>
        <p class="muted">${session.answered} of ${session.progress.ready} answered · ${session.correct} correct</p></div>
        <a class="button secondary small flat-button" href="#multiple-choice/${encodeURIComponent(session.id)}">${session.status === 'completed' ? 'Summary' : ['active','preparing','failed'].includes(session.status) ? 'Open session' : 'Details'}</a></li>`).join('')}</ul></div>`
        : '<p class="muted">Your Multiple-Choice sessions will appear here.</p>';
    } catch {
      if (active()) {
        list.innerHTML = '<p role="status" class="muted">Couldn’t load Multiple-Choice history.</p><button type="button" class="secondary small flat-button">Try again</button>';
        list.querySelector('button').onclick = () => void load();
      }
    } finally {
      loading = false;
    }
  }
  details.addEventListener('toggle', () => { if (details.open) void load(); });
}
