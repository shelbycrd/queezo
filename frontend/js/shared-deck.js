import {api} from './api.js';
import {app, busy, escape, mount} from './ui.js';
import {renderCardContent} from './card-content.js';
import {chooseStudy} from './study-options.js';

export async function sharedPage(token,route) {
  const deck = await api(`/shared/decks/${encodeURIComponent(token)}`);
  if (!mount(`<div class="deck-workspace"><div class="page-heading"><div><span class="badge">${deck.visibility === 'public' ? 'Public' : 'Unlisted'} deck</span><h1>${escape(deck.title)}</h1><p class="muted">${deck.cards.length} cards</p></div><div class="actions"><button id="copy-shared" class="secondary">Save private copy</button><button id="study-shared" ${deck.cards.length ? '' : 'disabled'}>Study a copy</button></div></div><div class="card-list">${deck.cards.map((card,index)=>`<article class="saved-card"><span class="content-label">Card ${index+1}</span>${renderCardContent(card.front,card.front_image,'Question photo')}<details class="shared-answer"><summary>Reveal answer</summary>${renderCardContent(card.back,card.back_image,'Answer photo')}</details></article>`).join('') || '<div class="empty">This deck has no cards yet.</div>'}</div></div>`,route)) return;
  const accountButtons = app.querySelector('.page-heading .actions');
  const copy = async study => busy(accountButtons, async () => {
    const created = await api(`/shared/decks/${encodeURIComponent(token)}/copy`,{method:'POST'});
    if (!accountButtons.isConnected || location.hash !== route) return;
    if (study) await chooseStudy(created.id);
    // Closing study options keeps the newly saved private copy accessible.
    if (location.hash === route) location.hash = `#deck/${created.id}`;
  });
  app.querySelector('#copy-shared').onclick = () => copy(false);
  app.querySelector('#study-shared').onclick = () => copy(true);
}
