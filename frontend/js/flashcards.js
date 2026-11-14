import {api} from './api.js';
import {startStudy} from './decks.js';
import {app, busy, date, duration, escape, mount, notice, plural} from './ui.js';

export async function deckPage(deckId, route) {
  const [deck, cards, sessions] = await Promise.all([api(`/decks/${deckId}`), api(`/decks/${deckId}/cards`), api(`/decks/${deckId}/sessions`)]);
  if (!mount(`<div class="breadcrumbs"><a href="#decks">Flashcards</a><span>/</span><span>Deck</span></div>
    <div class="page-heading"><div><p class="eyebrow">Study deck</p><h1>${escape(deck.title)}</h1><p class="muted">${cards.length} / 150 flashcards</p></div><div class="actions"><button id="rename" class="secondary">Rename</button><button id="delete-deck" class="danger">Delete deck</button><button id="study-deck" ${cards.length ? '' : 'disabled'}>Study deck →</button></div></div>
    <div class="section-heading"><h2>Flashcards <span class="muted">(${cards.length})</span></h2>${cards.length < 150 ? `<a class="button secondary small" href="#deck/${deckId}/add">+ Add cards</a>` : '<span class="badge">150-card limit reached</span>'}</div>
    ${cards.length ? `<div class="card-list">${cards.map((card, index) => `<article class="card-row"><div class="card-copy"><span class="badge">${index+1} · Question & answer</span><p>${escape(card.front)}</p><p class="answer">${escape(card.back)}</p></div><div class="actions"><a class="button secondary small" href="#deck/${deckId}/edit/${card.id}">Edit</a><button class="danger small" data-delete="${card.id}">Delete</button></div></article>`).join('')}</div>` : `<div class="empty"><h2>What do you want to remember?</h2><p class="muted">Add a question on the front and its answer on the back.</p><a class="button" href="#deck/${deckId}/add">Add your first card</a></div>`}
    <div class="section-heading"><h2>Recent study sessions</h2><span class="muted">Latest 50</span></div>
    ${sessions.length ? `<div class="panel"><ul class="history-list">${sessions.map(session => `<li><div><p>${escape(date(session.started_at))} · <strong>${escape(session.status)}</strong></p><p class="muted">${plural(session.total_reviews,'review')} · ${session.total_unique_cards} cards studied · ${duration(session.duration_seconds)}</p></div><a class="button secondary small" href="#${session.status === 'active' ? 'study' : 'summary'}/${session.session_id}">${session.status === 'active' ? 'Resume' : 'Summary'}</a></li>`).join('')}</ul></div>` : '<p class="muted">Your study sessions will appear here.</p>'}`, route)) return;

  app.querySelector('#rename').addEventListener('click', () => {
    const title = prompt('New deck title:', deck.title);
    if (title === null) return;
    busy(app, async () => { await api(`/decks/${deckId}`, {method:'PATCH', body:{title}}); await deckPage(deckId, route); notice('Deck renamed.', true); });
  });
  app.querySelector('#delete-deck').addEventListener('click', () => {
    if (!confirm(`Delete “${deck.title}”? This permanently removes its cards and study history.`)) return;
    busy(app, async () => { await api(`/decks/${deckId}`, {method:'DELETE'}); location.hash = '#decks'; notice('Deck deleted.', true); });
  });
  app.querySelector('#study-deck').addEventListener('click', () => busy(app, () => startStudy(deckId)));
  app.querySelectorAll('[data-delete]').forEach(button => button.addEventListener('click', () => {
    if (!confirm('Delete this flashcard? Existing study sessions keep their saved copy.')) return;
    busy(app, async () => { await api(`/cards/${button.dataset.delete}`, {method:'DELETE'}); await deckPage(deckId, route); notice('Flashcard deleted.', true); });
  }));
}

export async function cardForm(deckId, cardId, route) {
  const [deck, card] = await Promise.all([api(`/decks/${deckId}`), cardId ? api(`/cards/${cardId}`) : Promise.resolve(null)]);
  if (card && card.deck_id !== Number(deckId)) throw new Error('This card belongs to a different deck.');
  if (!card && deck.card_count >= 150) { location.hash = `#deck/${deckId}`; notice('This deck has reached the 150-card limit.'); return; }
  if (!mount(`<div class="form-panel"><div class="breadcrumbs"><a href="#deck/${deckId}">${escape(deck.title)}</a><span>/</span><span>${card ? 'Edit card' : 'Add cards'}</span></div>
    <div class="form-heading"><p class="eyebrow">Flashcards</p><h1>${card ? 'Edit your flashcard' : 'Build your recall'}</h1><p class="muted" id="card-count">${deck.card_count} / 150 cards saved</p></div>
    <form id="card-form" class="panel"><span class="badge">Question & answer</span>
    <label for="front">Front <span class="muted">(required)</span></label><textarea id="front" name="front" required maxlength="10000" placeholder="A question, term, or concept…">${escape(card?.front || '')}</textarea>
    <label for="back">Back <span class="muted">(required)</span></label><textarea id="back" name="back" required maxlength="10000" placeholder="The answer you want to remember…">${escape(card?.back || '')}</textarea>
    <p class="hint">Recall the answer, reveal the back, then rate how it felt.</p><div class="form-actions"><a class="button secondary" href="#deck/${deckId}">Cancel</a>${card ? '<button type="submit">Save changes</button>' : '<button class="secondary" type="submit" name="intent" value="next">Next Card</button><button type="submit" name="intent" value="finish" formnovalidate>Finish</button>'}</div></form></div>`, route)) return;
  const form = app.querySelector('#card-form');
  const back = form.elements.back;
  let count = deck.card_count;
  form.addEventListener('submit', event => {
    event.preventDefault();
    const finish = event.submitter?.value === 'finish';
    const empty = !form.elements.front.value.trim() && !back.value.trim();
    if (!card && finish && empty) { location.hash = `#deck/${deckId}`; return; }
    if (!form.reportValidity()) return;
    if (!form.elements.front.value.trim() || !back.value.trim()) { notice('Fill in both the question and answer.'); return; }
    busy(form, async () => {
      const body = {front:form.elements.front.value, back:back.value};
      await api(card ? `/cards/${cardId}` : `/decks/${deckId}/cards`, {method:card ? 'PATCH' : 'POST', body});
      if (!card) count++;
      if (location.hash !== route) return;
      if (card || finish || count >= 150) {
        location.hash = `#deck/${deckId}`;
        notice(count >= 150 ? 'Card saved. This deck now has 150 flashcards.' : 'Flashcard saved.', true);
      } else {
        form.elements.front.value = ''; back.value = '';
        app.querySelector('#card-count').textContent = `${count} / 150 cards saved`;
        form.elements.front.focus(); notice('Card saved. Ready for the next one.', true);
      }
    });
  });
}
