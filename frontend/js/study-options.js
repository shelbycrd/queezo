import {showNotice} from './popup.js';
import {api} from './api.js';
import {authenticatedUser} from './auth-state.js';

export function validateTiming(mode, scope, amount) {
  if (mode === 'unlimited') return {mode:'unlimited'};
  const value = Number(amount);
  if (!['number','string'].includes(typeof amount) || mode !== 'timed' || !['question','deck'].includes(scope) || !Number.isInteger(value) || value < 1 || value > (scope === 'question' ? 3600 : 180)) throw new Error('Choose a whole number within the time limit.');
  return {mode, scope, seconds:value * (scope === 'deck' ? 60 : 1)};
}
const timingKey = sessionId => `queezo.study-timing.${authenticatedUser()?.id}.${sessionId}`;
const memory = new Map();
export function saveTiming(sessionId, timing) {
  memory.set(timingKey(sessionId), timing);
  try { sessionStorage.setItem(timingKey(sessionId), JSON.stringify(timing)); } catch { /* In-memory timing still works. */ }
}
export function loadTiming(sessionId) {
  try {
    const value = memory.get(timingKey(sessionId)) || JSON.parse(sessionStorage.getItem(timingKey(sessionId)));
    if (value?.mode === 'timed' && ['question','deck'].includes(value.scope) && Number.isFinite(value.seconds) && value.seconds >= 1 && value.seconds <= 10800 && (!value.deadline || Number.isFinite(value.deadline))) return value;
  } catch { /* Old sessions are unlimited. */ }
  return {mode:'unlimited'};
}

let openDialog;
export function chooseStudy(deckId, {mode = 'classic'} = {}) {
  if (openDialog) return Promise.resolve();
  const accountId = authenticatedUser()?.id;
  const route = location.hash;
  return new Promise(resolve => {
    const dialog = document.createElement('dialog');
    openDialog = dialog;
    dialog.className = 'study-options-dialog';
    dialog.setAttribute('aria-labelledby','study-options-title');
    dialog.innerHTML = `<form id="study-options-form"><div class="dialog-heading"><h2 id="study-options-title">How would you like to study?</h2><button type="button" class="secondary small flat-button" id="cancel-study-options" aria-label="Close study options">×</button></div><fieldset class="study-type"><legend>Study mode</legend><div class="study-type-grid"><label><input type="radio" name="studyType" value="classic" checked><span><strong>Classic Mode</strong><small>Recall the answer and rate it.</small></span></label><label><input type="radio" name="studyType" value="multiple-choice"><span><strong>Multiple-Choice Mode</strong><small>Pick from four answers.</small></span></label></div></fieldset><fieldset id="classic-timing" class="classic-timing"><legend class="sr-only">Classic timing</legend><div class="study-mode-choices"><div class="study-mode-card"><label class="mode-selector"><input type="radio" name="mode" value="unlimited" checked><span class="mode-art" aria-hidden="true">∞</span><strong>Unlimited time</strong><span>Study at your own pace.</span></label></div><div class="study-mode-card"><label class="mode-selector"><input type="radio" name="mode" value="timed"><span class="mode-art" aria-hidden="true">◷</span><strong>Time bounded</strong><span>Give your practice a time limit.</span></label><div class="timed-options"><label for="study-scope">Apply limit to</label><select id="study-scope" name="scope"><option value="question">Per question</option><option value="deck">Entire deck</option></select><label><span id="time-amount-label">Seconds per question</span><input name="amount" type="number" min="1" max="3600" value="30" required></label><p class="hint" id="time-rule">When time runs out, the answer is revealed for you to rate.</p></div></div></div></fieldset><p id="study-options-error" class="inline-error" hidden></p><button class="start-learning" type="submit">Start studying</button></form>`;
    document.body.append(dialog);
    const form = dialog.querySelector('form');
    form.noValidate = true;
    form.elements.studyType.value = mode;
    const classicTiming = dialog.querySelector('#classic-timing');
    function showTiming() {
      const classic = form.elements.studyType.value === 'classic';
      classicTiming.hidden = !classic;
      classicTiming.disabled = !classic;
    }
    showTiming();
    const finish = () => { if (openDialog === dialog) openDialog = null; dialog.remove(); resolve(); };
    dialog.addEventListener('close', finish, {once:true});
    dialog.querySelector('#cancel-study-options').onclick = () => dialog.close();
    form.addEventListener('change', event => {
      if (event.target.name === 'studyType') showTiming();
      if (event.target.name === 'scope') {
        const perQuestion = form.elements.scope.value === 'question';
        form.elements.amount.value = perQuestion ? '30' : '10';
        form.elements.amount.max = perQuestion ? '3600' : '180';
        dialog.querySelector('#time-amount-label').textContent = perQuestion ? 'Seconds per question' : 'Minutes for the deck';
        dialog.querySelector('#time-rule').textContent = perQuestion ? 'When time runs out, the answer is revealed for you to rate.' : 'When time runs out, the study session ends.';
      }
    });
    form.addEventListener('submit', async event => {
      event.preventDefault();
      const button = form.querySelector('[type=submit]');
      if (button.disabled) return;
      const multiple = form.elements.studyType.value === 'multiple-choice';
      try {
        const timing = multiple ? null :
          validateTiming(form.elements.mode.value, form.elements.scope.value, form.elements.amount.value);
        button.disabled = true;
        const session = await api(`/decks/${deckId}/${multiple ? 'multiple-choice' : 'study'}`, {method:'POST'});
        if (authenticatedUser()?.id !== accountId) { dialog.close(); return; }
        if (!dialog.open || location.hash !== route) {
          const exit = multiple ? `/multiple-choice/${session.id}/cancel` : `/study/${session.id}/exit`;
          void api(exit, {method:'POST'}).catch(() => {});
          return;
        }
        if (timing) saveTiming(session.id, timing);
        dialog.close();
        location.hash = `#${multiple ? 'multiple-choice' : 'study'}/${session.id}`;
      } catch (failure) {
        if (!dialog.open || location.hash !== route || authenticatedUser()?.id !== accountId) return;
        const message = multiple && failure.status === 0
          ? 'Could not confirm the new session. Check Multiple-Choice history on your deck before trying again.'
          : failure.message;
        showNotice(message);
        button.disabled = false;
      }
    });
    dialog.showModal();
  });
}
export function closeStudyOptions() { openDialog?.close(); }
