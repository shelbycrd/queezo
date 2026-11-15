import {api} from './api.js';
import {startStudy} from './decks.js';
import {app, busy, date, duration, escape, mount, notice, plural} from './ui.js';
import {MAX_IMAGE_BYTES, renderCardContent, safeImageUrl} from './card-content.js';
import {playPageTurn, preparePageSound} from './audio.js';

export const deckPage = (deckId, route) => deckWorkspace(deckId, null, route);
export const cardForm = (deckId, cardId, route) => deckWorkspace(deckId, cardId, route);

function editorSide(side, title, placeholder, text) {
  return `<section class="editor-side"><label for="${side}">${title}</label><textarea id="${side}" name="${side}" required maxlength="10000" placeholder="${placeholder}">${escape(text)}</textarea>
    <div class="editor-toolbar"><label class="photo-picker" for="${side}-photo">＋ Photo<input class="sr-only" type="file" id="${side}-photo" accept="image/png,image/jpeg,image/webp" aria-label="Add photo to ${title.toLowerCase()}"></label></div>
    <div id="${side}-image-preview" class="image-preview" hidden></div></section>`;
}

async function readPhoto(file) {
  if (!['image/png','image/jpeg','image/webp'].includes(file.type)) throw new Error('Choose a PNG, JPG, or WebP photo.');
  if (file.size > MAX_IMAGE_BYTES) throw new Error('Choose a photo smaller than 1.5 MB.');
  const source = await new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = () => reject(new Error('This photo could not be read. Try another image.'));
    reader.readAsDataURL(file);
  });
  if (!safeImageUrl(source)) throw new Error('This photo could not be read. Try another image.');
  const photo = new Image();
  photo.src = source;
  try { await photo.decode(); } catch { throw new Error('This file is not a readable photo.'); }
  if (photo.naturalWidth * photo.naturalHeight > 16000000) throw new Error('Choose a photo no larger than 16 megapixels.');
  return source;
}

async function deckWorkspace(deckId, cardId, route) {
  const [deck, fetchedCards, sessions] = await Promise.all([api(`/decks/${deckId}`), api(`/decks/${deckId}/cards`), api(`/decks/${deckId}/sessions`)]);
  let cards = fetchedCards;
  const editing = cardId ? cards.find(card => card.id === Number(cardId)) : null;
  if (cardId && !editing) throw new Error('This card was not found in this deck.');
  if (!mount(`<div class="deck-workspace"><div class="breadcrumbs"><a href="#decks">Flashcards</a><span>/</span><span>${escape(deck.title)}</span></div>
    <div class="page-heading"><div><p class="eyebrow">Your study deck</p><h1>${escape(deck.title)}</h1><p class="muted"><span data-card-count>${cards.length}</span> / 150 cards</p></div><div class="actions"><button id="rename" class="secondary small">Rename</button><button id="delete-deck" class="danger small">Delete deck</button></div></div>
    <form id="card-form" class="card-composer panel" novalidate><fieldset class="editor-fields"><legend class="sr-only">${editing ? 'Edit flashcard' : 'Create a flashcard'}</legend><div class="composer-heading"><h2>${editing ? 'Edit this card' : 'Make something memorable'}</h2><span class="badge">Question + answer</span></div>
      <div class="editor-sides">${editorSide('front','Question','What do you want to remember?', editing?.front || '')}${editorSide('back','Answer','Write the answer here…', editing?.back || '')}</div>
      <p class="hint">Both sides need text. Add a photo to either side if you need one.</p><div class="composer-actions"><span id="card-count" class="muted" role="status" aria-live="polite"><span data-card-count>${cards.length}</span> cards saved</span><div class="actions">${editing ? `<a href="#deck/${deckId}" class="button secondary">Cancel edit</a>` : ''}<button type="submit" id="next-card" data-intent="save">${editing ? 'Save changes' : 'Next Card →'}</button><button type="submit" id="study-deck" data-intent="study" class="secondary">Study deck</button></div></div></fieldset></form>
    <div class="section-heading"><h2>Cards <span class="muted">(<span data-card-count>${cards.length}</span>)</span></h2><label class="sr-only" for="card-order">Card order</label><select id="card-order" class="card-order"><option value="desc">Most recent first</option><option value="asc">Least recent first</option></select></div><div id="saved-cards" class="card-list"></div>
    <details class="session-history"><summary>Recent study sessions <span class="muted">(${sessions.length})</span></summary>${sessions.length ? `<div class="panel"><ul class="history-list">${sessions.map(session => `<li><div><p>${escape(date(session.started_at))} · <strong>${escape(session.status)}</strong></p><p class="muted">${plural(session.total_reviews,'review')} · ${session.total_unique_cards} cards studied · ${duration(session.duration_seconds)}</p></div><a class="button secondary small" href="#${session.status === 'active' ? 'study' : 'summary'}/${session.session_id}">${session.status === 'active' ? 'Resume' : 'Summary'}</a></li>`).join('')}</ul></div>` : '<p class="muted">Your sessions will appear here.</p>'}</details></div>`, route)) return;

  const form = app.querySelector('#card-form');
  const fields = form.querySelector('fieldset');
  const savedCards = app.querySelector('#saved-cards');
  const images = {front:editing?.front_image || null, back:editing?.back_image || null};
  const revisions = {front:0, back:0};
  let newestFirst = true;
  let pending = false;
  let photosPending = 0;

  function updateCount() {
    app.querySelectorAll('[data-card-count]').forEach(element => { element.textContent = cards.length; });
    const full = !editing && cards.length >= 150;
    form.querySelector('#next-card').disabled = full;
    for (const side of ['front','back']) {
      form.elements[side].disabled = full;
      form.querySelector(`#${side}-photo`).disabled = full;
    }
  }
  function renderSaved() {
    savedCards.innerHTML = cards.length ? [...cards].sort((a,b) => (newestFirst ? -1 : 1) * (a.id-b.id)).map((card, index) => `<article class="saved-card ${card.id === editing?.id ? 'is-editing' : ''}"><div class="saved-card-heading"><span class="badge">Card ${cards.indexOf(card) + 1}</span><div class="actions"><a class="button secondary small card-icon-action flat-button" aria-label="Edit card ${cards.indexOf(card) + 1}" title="Edit card" href="#deck/${deckId}/edit/${card.id}"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d="m15 4 5 5M4 20l5-1L20 8a3.5 3.5 0 0 0-5-5L4 14z"/></svg></a><button type="button" class="danger small card-icon-action flat-button" data-delete="${card.id}" aria-label="Delete card ${cards.indexOf(card) + 1}" title="Delete card"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d="M4 6h16M9 6V3h6v3M6 6l1 15h10l1-15M10 10v7m4-7v7"/></svg></button></div></div><div class="saved-card-sides"><div class="saved-side"><span class="content-label">Question</span>${renderCardContent(card.front, card.front_image, 'Question photo')}</div><div class="saved-side answer"><span class="content-label">Answer</span>${renderCardContent(card.back, card.back_image, 'Answer photo')}</div></div></article>`).join('') : '<div class="empty"><h2>Your first card starts above.</h2><p class="muted">Write a question and its answer, then choose Next Card.</p></div>';
    updateCount();
  }
  function renderPhoto(side) {
    const preview = form.querySelector(`#${side}-image-preview`);
    preview.hidden = !images[side];
    preview.innerHTML = images[side] ? `<img class="card-photo" src="${safeImageUrl(images[side])}" alt="${side === 'front' ? 'Question' : 'Answer'} photo preview"><button class="secondary small" type="button" data-remove-image="${side}">Remove photo</button>` : '';
  }
  for (const side of ['front','back']) {
    renderPhoto(side);
    const input = form.querySelector(`#${side}-photo`);
    input.addEventListener('change', async () => {
      const file = input.files?.[0];
      if (!file || pending) return;
      const revision = ++revisions[side];
      photosPending++;
      try {
        const source = await readPhoto(file);
        if (!form.isConnected || revision !== revisions[side]) return;
        images[side] = source;
        renderPhoto(side);
      } catch (error) { if (form.isConnected) notice(error.message); }
      finally { photosPending--; input.value = ''; }
    });
  }
  form.addEventListener('click', event => {
    const remove = event.target.closest('[data-remove-image]');
    if (remove && !pending) {
      const side = remove.dataset.removeImage;
      revisions[side]++; images[side] = null; renderPhoto(side);
    }

  });
  form.addEventListener('submit', async event => {
    event.preventDefault();
    if (pending) return;
    if (photosPending) { notice('Wait a moment for the photo to finish loading.'); return; }
    const study = event.submitter?.dataset.intent === 'study';
    const hasDraft = !!(form.elements.front.value.trim() || form.elements.back.value.trim() || images.front || images.back);
    const shouldSave = editing || hasDraft || !study;
    if (shouldSave && (!form.reportValidity() || !form.elements.front.value.trim() || !form.elements.back.value.trim())) { notice('Write both a question and an answer before saving.'); return; }
    if (shouldSave && !editing && cards.length >= 150) { notice('This deck has reached its 150-card limit.'); return; }
    if (!shouldSave && !cards.length) { notice('Add your first card before starting a study session.'); return; }
    if (!study && !editing) preparePageSound();
    pending = true; fields.disabled = true;
    try {
      if (shouldSave) {
        const body = {front:form.elements.front.value, back:form.elements.back.value, front_image:images.front, back_image:images.back};
        const saved = await api(editing ? `/cards/${editing.id}` : `/decks/${deckId}/cards`, {method:editing ? 'PATCH' : 'POST', body});
        if (!form.isConnected || location.hash !== route) return;
        cards = editing ? cards.map(card => card.id === saved.id ? saved : card) : [...cards,saved];
        if (!study && !editing) playPageTurn();
        if (editing && !study) { location.hash = `#deck/${deckId}`; return; }
        if (!editing) {
          form.elements.front.value = ''; form.elements.back.value = '';
          for (const side of ['front','back']) { revisions[side]++; images[side] = null; renderPhoto(side); }
        }
        renderSaved(); notice('');
        if (!study && !editing) {
          const increment = document.createElement('span');
          increment.className = 'saved-increment'; increment.textContent = '+1'; increment.setAttribute('aria-hidden','true');
          app.querySelector('#card-count').append(increment);
          setTimeout(() => increment.remove(),1000);
        }
      }
      if (study) await startStudy(deckId);
    } catch (error) { if (form.isConnected) notice(error.message); }
    finally {
      pending = false; fields.disabled = false;
      if (form.isConnected) { updateCount(); if (!study && !editing) form.elements.front.focus(); }
    }
  });
  app.querySelector('#rename').addEventListener('click', () => {
    const title = prompt('New deck title:', deck.title);
    if (title === null) return;
    busy(app, async () => { await api(`/decks/${deckId}`, {method:'PATCH', body:{title}}); await deckWorkspace(deckId, cardId, route); });
  });
  app.querySelector('#delete-deck').addEventListener('click', () => {
    if (!confirm(`Delete “${deck.title}”? This permanently removes its cards and study history.`)) return;
    busy(app, async () => { await api(`/decks/${deckId}`, {method:'DELETE'}); location.hash = '#decks'; });
  });
  savedCards.addEventListener('click', event => {
    const button = event.target.closest('[data-delete]');
    if (!button || !confirm('Delete this flashcard? Existing study sessions keep their saved copy.')) return;
    busy(savedCards, async () => {
      await api(`/cards/${button.dataset.delete}`, {method:'DELETE'});
      if (!form.isConnected) return;
      if (Number(button.dataset.delete) === editing?.id) { location.hash = `#deck/${deckId}`; return; }
      cards = cards.filter(card => card.id !== Number(button.dataset.delete)); renderSaved();
    });
  });
  app.querySelector('#card-order').addEventListener('change', event => { newestFirst = event.target.value === 'desc'; renderSaved(); });
  renderSaved();
  if (route.endsWith('/add') || editing) form.elements.front.focus();
}
