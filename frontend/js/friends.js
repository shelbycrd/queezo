import {api} from './api.js';
import {authenticatedUser} from './auth-state.js';
import {communityTile} from './deck-view.js';
import {escape, mount, notice, plural} from './ui.js';

function friendRow(friend) {
  const name = escape(friend.display_name);
  const username = encodeURIComponent(friend.username);
  const status = friend.online ? 'Online' : 'Offline';
  const initial = escape(Array.from(friend.display_name.trim())[0]?.toUpperCase() || '?');
  return `<details class="friend-row" data-friend="${escape(friend.username)}" name="friend-actions">
    <summary><span class="friend-avatar" aria-hidden="true">${initial}<span class="presence-dot ${status.toLowerCase()}"></span></span>
      <span class="friend-name"><strong>${name}</strong><small>${status}</small></span><span class="friend-chevron" aria-hidden="true">⌄</span></summary>
    <div class="friend-actions"><a class="button secondary small flat-button" href="#friend/${username}">View Profile</a>
      <button class="secondary small flat-button" type="button" disabled>Invite for a study session</button></div>
  </details>`;
}

export function initFriends() {
  const trigger = document.querySelector('#open-friends');
  const drawer = document.createElement('dialog');
  drawer.id = 'friends-drawer';
  drawer.setAttribute('aria-labelledby', 'friends-heading');
  drawer.innerHTML = `<div class="friends-content">
    <div class="drawer-heading"><h2 id="friends-heading">Friends</h2><button type="button" class="secondary flat-button" aria-label="Close friends">×</button></div>
    <label class="sr-only" for="friend-search">Search friends</label>
    <input id="friend-search" type="search" placeholder="Search friends…" autocomplete="off" autofocus>
    <div id="friend-list" aria-busy="false"></div>
    <details class="friend-requests"><summary id="friend-requests-label">Friend requests</summary>
      <form id="add-friend"><label for="friend-username">Add by username</label>
        <div class="friend-request-form"><input id="friend-username" name="username" required minlength="3" maxlength="32" pattern="[A-Za-z0-9_]{3,32}" autocomplete="off" placeholder="Username">
        <button type="submit" class="small">Send request</button></div></form>
      <div id="friend-request-list"></div>
    </details>
  </div>`;
  document.body.append(drawer);

  const search = drawer.querySelector('#friend-search');
  const list = drawer.querySelector('#friend-list');
  const requests = drawer.querySelector('#friend-request-list');
  const requestPanel = drawer.querySelector('.friend-requests');
  const form = drawer.querySelector('#add-friend');
  let data = null;
  let drawerVersion = 0;
  let refreshVersion = 0;
  let responding = false;

  function renderFriends() {
    const open = list.querySelector('details[open]')?.dataset.friend;
    const query = search.value.trim().toLocaleLowerCase();
    const friends = data.friends.filter(friend =>
      [friend.username, friend.display_name].some(value => value.toLocaleLowerCase().includes(query)));
    friends.sort((a, b) => Number(b.online) - Number(a.online));
    list.innerHTML = friends.length ? friends.map(friendRow).join('') :
      `<p class="friend-empty">${query ? 'No friends match your search.' : 'No friends yet. Send a request by username.'}</p>`;
    for (const row of list.querySelectorAll('details')) row.open = row.dataset.friend === open;
  }

  function renderRequests() {
    drawer.querySelector('#friend-requests-label').textContent = data.incoming.length
      ? `Friend requests (${data.incoming.length})` : 'Friend requests';
    requests.innerHTML = data.incoming.map(person => `<div class="friend-request">
      <strong>${escape(person.display_name)}</strong> <small>@${escape(person.username)}</small>
      <div class="actions"><button class="small" type="button" data-from="${escape(person.username)}" data-decision="accept">Accept</button>
      <button class="secondary flat-button small" type="button" data-from="${escape(person.username)}" data-decision="decline">Decline</button></div>
    </div>`).join('') + data.outgoing.map(person =>
      `<p class="friend-request">Pending · @${escape(person.username)}</p>`).join('');
  }

  async function refresh({background = false} = {}) {
    const version = ++refreshVersion;
    try {
      const next = await api('/friends');
      if (version !== refreshVersion || !drawer.open) return;
      if (!data || JSON.stringify(next.friends) !== JSON.stringify(data.friends)) {
        // Leave the focused row in place while the user is using its links.
        if (background && list.contains(document.activeElement)) next.friends = data.friends;
        else {
          data = {...data, friends: next.friends};
          renderFriends();
        }
      }
      if (JSON.stringify(next.incoming) !== JSON.stringify(data?.incoming) ||
          JSON.stringify(next.outgoing) !== JSON.stringify(data?.outgoing)) {
        if (background && requests.contains(document.activeElement)) {
          next.incoming = data.incoming;
          next.outgoing = data.outgoing;
        } else {
          data = next;
          renderRequests();
        }
      }
      data = next;
      document.querySelectorAll('[data-friend-count]').forEach(element => {
        element.textContent = data.friends.length;
      });
    } catch (error) {
      if (!background && version === refreshVersion && drawer.open) {
        if (!data) list.textContent = 'Couldn’t load your friends.';
        notice(error.message);
      }
    } finally {
      if (version === refreshVersion) list.setAttribute('aria-busy', 'false');
    }
  }

  trigger.setAttribute('aria-haspopup', 'dialog');
  trigger.setAttribute('aria-controls', drawer.id);
  trigger.setAttribute('aria-expanded', 'false');
  trigger.onclick = () => {
    if (!authenticatedUser() || drawer.open) return;
    document.querySelector('#notifications-panel')?.close();
    ++drawerVersion;
    data = null;
    search.value = '';
    form.reset();
    form.querySelector('button').disabled = false;
    requestPanel.open = false;
    drawer.querySelector('#friend-requests-label').textContent = 'Friend requests';
    requests.replaceChildren();
    list.textContent = 'Loading friends…';
    list.setAttribute('aria-busy', 'true');
    drawer.showModal();
    trigger.setAttribute('aria-expanded', 'true');
    void refresh();
  };
  drawer.querySelector('.drawer-heading button').onclick = () => drawer.close();
  drawer.addEventListener('click', event => {
    if (event.target === drawer || event.target.closest('.friend-actions a')) drawer.close();
  });
  drawer.addEventListener('close', () => {
    trigger.setAttribute('aria-expanded', 'false');
    ++drawerVersion;
    ++refreshVersion;
    responding = false;
  });
  search.addEventListener('input', () => { if (data) renderFriends(); });

  form.addEventListener('submit', async event => {
    event.preventDefault();
    const version = drawerVersion;
    const button = form.querySelector('button');
    button.disabled = true;
    try {
      await api('/friends/requests', {method:'POST', body:{username:form.elements.username.value}});
      if (version !== drawerVersion || !drawer.open) return;
      form.reset();
      await refresh();
      if (version === drawerVersion && drawer.open) notice('Friend request sent.', true);
    } catch (error) {
      if (version === drawerVersion && drawer.open) notice(error.message);
    } finally {
      if (version === drawerVersion) button.disabled = false;
    }
  });

  requests.addEventListener('click', async event => {
    const button = event.target.closest('[data-decision]');
    if (!button || responding) return;
    const version = drawerVersion;
    responding = true;
    button.disabled = true;
    try {
      await api(`/friends/requests/${encodeURIComponent(button.dataset.from)}/respond`, {
        method:'POST', body:{decision:button.dataset.decision},
      });
      if (version === drawerVersion && drawer.open) await refresh();
    } catch (error) {
      if (version === drawerVersion && drawer.open) notice(error.message);
    } finally {
      if (version === drawerVersion) {
        responding = false;
        button.disabled = false;
      }
    }
  });

  let presenceInFlight = false;
  async function pulse() {
    if (!authenticatedUser() || document.hidden || presenceInFlight) return;
    presenceInFlight = true;
    try {
      await api('/friends/presence', {method:'POST'});
    } catch {
      // Network or session changes should not interrupt study with presence errors.
    } finally {
      presenceInFlight = false;
    }
  }
  setInterval(() => void pulse(), 45000);
  document.addEventListener('visibilitychange', () => { void pulse(); });
  setInterval(() => {
    if (drawer.open && data && !document.hidden && !responding && !form.querySelector('button').disabled) {
      void refresh({background:true});
    }
  }, 15000);
  window.addEventListener('hashchange', () => { if (drawer.open) drawer.close(); });
  return {
    reset() {
      if (drawer.open) drawer.close();
      ++drawerVersion;
      ++refreshVersion;
      data = null;
      list.replaceChildren();
      requests.replaceChildren();
    },
    pulse,
  };
}

export async function friendProfile(username, route) {
  const friend = await api(`/friends/${encodeURIComponent(username)}/profile`);
  const initial = escape(Array.from(friend.display_name.trim())[0]?.toUpperCase() || '?');
  mount(`<section class="panel profile-card friend-profile">
    <div class="profile-avatar" aria-hidden="true">${initial}</div>
    <div class="profile-identity"><h1>${escape(friend.display_name)}</h1><p class="profile-username">@${escape(friend.username)}</p></div>
  </section><section class="profile-public"><div class="section-heading"><h2>Public Decks</h2><span class="deck-total">${plural(friend.public_decks.length,'deck')}</span></div>
  ${friend.public_decks.length ? `<div class="deck-grid">${friend.public_decks.map(communityTile).join('')}</div>` : '<p class="empty">No public decks yet.</p>'}</section>`, route);
}
