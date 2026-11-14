import {api} from './api.js';
import {app, busy, escape, mount, notice, plural} from './ui.js';

export async function dashboard(route) {
  const stats = await api('/dashboard');
  if (!mount(`<p class="eyebrow">Your study space</p><h1>Small tools. Steady progress.</h1>
    <p class="muted">Practice your recall, check your grades, and make time to focus.</p>
    <div class="app-grid">
      <section class="panel tool-card"><span class="tool-number" aria-hidden="true">01</span><p class="eyebrow">App 1</p><h2>Flashcards</h2><p class="muted">A question on the front. An answer on the back. Build a deck and practice at your own pace.</p><p class="tool-meta">${plural(stats.deck_count,'deck')} · ${plural(stats.card_count,'card')}</p><a class="button" href="#decks">Open Flashcards →</a></section>
      <section class="panel tool-card"><span class="tool-number" aria-hidden="true">02</span><p class="eyebrow">App 2</p><h2>GWA Calculator</h2><p class="muted">Enter your course units and grades to calculate your general weighted average and honor standing.</p><p class="tool-meta">1–15 courses · Grades from 1.00 to 5.00</p><a class="button" href="#gwa">Calculate my GWA →</a></section>
      <section class="panel tool-card"><span class="tool-number" aria-hidden="true">03</span><p class="eyebrow">App 3</p><h2>Pomodoro Timer</h2><p class="muted">Work in focused intervals, take a break, and move through your task queue one pomodoro at a time.</p><p class="tool-meta">25 min study · 5 min short · 15 min long</p><a class="button" href="#pomodoro">Start focusing →</a></section>
    </div>`, route)) return;
}

export async function decks(route) {
  const items = await api('/decks');
  if (!mount(`<div class="page-heading"><div><p class="eyebrow">Flashcards</p><h1>Your decks</h1><p class="muted">One topic per deck. Up to 150 cards per topic.</p></div><span class="muted">${plural(items.length,'deck')}</span></div>
    <form id="new-deck" class="inline-form"><label for="deck-title">New deck title</label><input id="deck-title" name="title" required maxlength="120" placeholder="Name a subject or topic…" autocomplete="off"><button type="submit">+ Create deck</button></form>
    ${items.length ? `<div class="deck-grid">${items.map(deck => `<article class="deck-card"><div class="deck-meta"><span>STUDY DECK</span><span>${deck.card_count} / 150 cards</span></div><h3>${escape(deck.title)}</h3><p class="muted">${deck.card_count ? 'Ready when you are.' : 'Add your first flashcard to get started.'}</p><div class="actions"><a class="button secondary small" href="#deck/${deck.id}">Open deck</a><button class="small" data-study="${deck.id}" ${deck.card_count ? '' : 'disabled'}>Study →</button></div></article>`).join('')}</div>` : `<div class="empty"><h2>A fresh start</h2><p class="muted">Create your first deck above, then fill it with what you want to remember.</p></div>`}`, route)) return;
  app.querySelector('#new-deck').addEventListener('submit', event => {
    event.preventDefault();
    const form = event.currentTarget;
    busy(form, async () => {
      const deck = await api('/decks', {method:'POST', body:{title:form.elements.title.value}});
      location.hash = `#deck/${deck.id}`;
      notice('Deck created.', true);
    });
  });
  app.querySelectorAll('[data-study]').forEach(button => button.addEventListener('click', () => busy(button.parentElement, () => startStudy(button.dataset.study))));
}

export async function startStudy(deckId) {
  const session = await api(`/decks/${deckId}/study`, {method:'POST'});
  location.hash = `#study/${session.id}`;
}
