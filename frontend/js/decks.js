import {api} from './api.js';
import {app, busy, escape, mount, notice, plural} from './ui.js';
import {icon} from './icons.js';

import {deckTile} from './deck-view.js';
import {chooseStudy} from './study-options.js';

export async function dashboard(route) {
  const [stats, activity, recent] = await Promise.all([api('/dashboard'),api('/dashboard/activity'),api('/decks')]);
  recent.sort((a,b) => b.created_at.localeCompare(a.created_at) || b.id-a.id);
  const today = new Date(`${activity.today}T00:00:00Z`);
  const days = Array.from({length:7}, (_, i) => {
    const day = new Date(today); day.setUTCDate(day.getUTCDate() - 6 + i);
    const key = day.toISOString().slice(0,10);
    return `<div class="week-day ${activity.active_days.includes(key) ? 'studied' : ''}"><span>${day.toLocaleDateString('en',{weekday:'narrow',timeZone:'UTC'})}</span><span class="day-dot" aria-label="${key}: ${activity.active_days.includes(key) ? 'studied' : 'no study recorded'}">${activity.active_days.includes(key) ? '✓' : '·'}</span></div>`;
  }).join('');
  if (!mount(`<div class="page-heading"><div><h1>Home</h1></div></div>
    <section class="home-welcome"><div><h2>What will you<br>learn today?</h2><p>Pick up a card and take it<br>one small step at a time.</p><div class="actions"><a class="button" href="#decks">Open flashcards ${icon('arrow')}</a><a class="text-link" href="#pomodoro">Start focusing</a></div></div><div class="welcome-art" aria-hidden="true"><div class="art-orbit"></div><div class="art-card art-back"></div><div class="art-card art-front"><span>Q</span><i></i><i></i><i></i></div></div></section>
    <section class="recent-section"><div class="section-heading"><div><h2>Your latest decks</h2><p class="muted">Your most recently created decks.</p></div><div class="carousel-controls"><button type="button" id="recent-prev" class="icon-button secondary" aria-label="Previous decks">←</button><button type="button" id="recent-next" class="icon-button secondary" aria-label="Next decks">→</button></div></div>
    ${recent.length ? `<div class="recent-track" id="recent-track" tabindex="0" aria-label="Latest decks, newest first">${recent.slice(0,12).map(deckTile).join('')}</div>` : '<div class="empty"><div class="empty-icon">'+icon('cards')+'</div><h3>Your first deck starts here.</h3><p class="muted">Create a deck and add something you want to remember.</p><a class="button secondary" href="#decks">Create a deck</a></div>'}</section>
    <div class="home-lower"><section class="panel streak-panel"><div class="section-heading"><h2>Your study rhythm</h2></div><div class="streak-number">${activity.study_streak}<span> day${activity.study_streak === 1 ? '' : 's'} in a row</span></div><p class="muted">${activity.active_today ? 'You made time to learn today. Keep it going!' : 'A flashcard review or finished pomodoro keeps your streak going.'}</p><div class="study-week">${days}</div><div class="home-counts"><span><strong>${stats.deck_count}</strong> decks</span><span><strong>${stats.card_count}</strong> flashcards</span></div></section>
      <section class="panel friends-panel"><div class="section-heading"><h2>Your study circle</h2><span class="badge">Coming soon</span></div><div class="friend-tabs" aria-label="Friend presence"><button type="button" id="friends-online" aria-pressed="true">Online <span>0</span></button><button type="button" id="friends-offline" aria-pressed="false">Offline <span>0</span></button></div><div class="friends-empty"><div class="empty-icon">${icon('friends')}</div><h3 id="friends-message">No friends online yet.</h3><p class="muted">A little room for learning together.<br>Your friends will appear here once connected.</p></div></section></div>`, route)) return;
  app.querySelectorAll('[data-study]').forEach(button => button.addEventListener('click', () => busy(button.parentElement, () => startStudy(button.dataset.study))));
  const track = app.querySelector('#recent-track');
  const prev = app.querySelector('#recent-prev'), next = app.querySelector('#recent-next');
  const update = () => { prev.disabled = !track || track.scrollLeft <= 1; next.disabled = !track || track.scrollLeft + track.clientWidth >= track.scrollWidth - 2; };
  prev.addEventListener('click', () => track?.scrollBy({left:-300,behavior:matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth'}));
  next.addEventListener('click', () => track?.scrollBy({left:300,behavior:matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth'}));
  track?.addEventListener('scroll',update); update();
  for (const mode of ['online','offline']) app.querySelector(`#friends-${mode}`).addEventListener('click', () => {
    app.querySelector('#friends-message').textContent = mode === 'online' ? 'No friends online yet.' : 'No offline friends yet.';
    for (const item of ['online','offline']) app.querySelector(`#friends-${item}`).setAttribute('aria-pressed',String(mode === item));
  });
}

export async function decks(route) {
  const items = await api('/decks');
  items.sort((a,b) => b.created_at.localeCompare(a.created_at) || b.id-a.id);
  if (!mount(`<div class="page-heading"><div><h1>Your Decks</h1></div><span class="deck-total">${plural(items.length,'deck')}</span></div>
    <div class="deck-tools"><form id="deck-search" class="new-deck-form" role="search"><div><label for="deck-search-input">Search decks</label><input id="deck-search-input" type="search" placeholder="Search your decks…" autocomplete="off"></div><button type="submit" class="secondary">Search</button></form><button id="open-create-deck" type="button">${icon('plus')} Create Deck</button></div>
    <dialog id="create-deck-dialog" class="create-deck-dialog"><form id="new-deck"><h2>Create a deck</h2><label for="deck-title">Deck title</label><input id="deck-title" name="title" required maxlength="120" autocomplete="off"><div class="actions"><button id="cancel-create-deck" type="button" class="secondary">Cancel</button><button type="submit">Create Deck</button></div></form></dialog>
    <p id="deck-search-empty" class="empty" hidden>No decks match your search.</p>
    ${items.length ? `<div class="deck-grid">${items.map(deckTile).join('')}</div>` : '<div class="empty"><h2>Something worth remembering?</h2><p class="muted">Create your first deck, then add your questions and answers.</p></div>'}`,route)) return;
  const dialog = app.querySelector('#create-deck-dialog');
  app.querySelector('#open-create-deck').addEventListener('click', () => dialog.showModal());
  app.querySelector('#cancel-create-deck').addEventListener('click', () => dialog.close());
  const search = () => {
    const query = app.querySelector('#deck-search-input').value.trim().toLocaleLowerCase();
    let matches = 0;
    app.querySelectorAll('.portrait-deck').forEach((tile, index) => {
      tile.hidden = !items[index].title.toLocaleLowerCase().includes(query);
      if (!tile.hidden) matches++;
    });
    app.querySelector('#deck-search-empty').hidden = !items.length || matches > 0;
  };
  app.querySelector('#deck-search').addEventListener('submit', event => { event.preventDefault(); search(); });
  app.querySelector('#deck-search-input').addEventListener('input', search);
  app.querySelector('#new-deck').addEventListener('submit', event => {
    event.preventDefault(); const form = event.currentTarget;
    busy(form, async () => { const deck = await api('/decks',{method:'POST',body:{title:form.elements.title.value}}); dialog.close(); location.hash=`#deck/${deck.id}`; });
  });
  app.querySelectorAll('[data-study]').forEach(button => button.addEventListener('click', () => busy(button.parentElement, () => startStudy(button.dataset.study))));
}

export async function startStudy(deckId) {
  await chooseStudy(deckId);
}
