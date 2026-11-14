import {escape, plural} from './ui.js';
import {icon} from './icons.js';

const colors = new Map();
const pastels = ['lilac','peach','mint','blue','rose','butter','aqua'];
let remainingColors = [];
export function deckTile(deck) {
  if (!colors.has(deck.id)) {
    if (!remainingColors.length) {
      remainingColors = [...pastels];
      for (let index = remainingColors.length - 1; index > 0; index--) {
        const other = Math.floor(Math.random() * (index + 1));
        [remainingColors[index], remainingColors[other]] = [remainingColors[other], remainingColors[index]];
      }
    }
    colors.set(deck.id, remainingColors.pop());
  }
  return `<article class="deck-card portrait-deck ${colors.get(deck.id)}"><a class="deck-cover" href="#deck/${deck.id}" aria-label="Open ${escape(deck.title)}"><span class="deck-cover-icon">${icon('cards')}</span><span class="deck-cover-lines" aria-hidden="true"></span><span class="deck-cover-label">MADE TO REMEMBER</span></a><div class="deck-card-body"><h2><a href="#deck/${deck.id}">${escape(deck.title)}</a></h2><p class="muted">${plural(deck.card_count,'flashcard')}</p><div class="actions"><a class="button secondary small flat-button" href="#deck/${deck.id}">Open deck</a><button class="small" data-study="${deck.id}" ${deck.card_count ? '' : 'disabled'}>Study ${icon('arrow')}</button></div></div></article>`;
}
