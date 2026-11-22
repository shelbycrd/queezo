<script setup>
import {computed, onScopeDispose, ref, shallowRef, watch} from 'vue';
import {api} from '../../js/api.js';
import {account} from '../services/session.js';
import {friendsOpen, friendCount, closeFriends} from '../services/friends.js';
import {showNotice} from '../services/notice.js';
import {useEvent} from '../composables/lifecycle.js';
import {buttonFeedback as vButtonFeedback} from './ButtonFeedback.js';
import {profilePath} from '../services/profiles.js';

const drawer = ref(), search = ref(''), username = ref(''), requestPanel = ref();
const list = ref(), requests = ref(), data = shallowRef(null);
const busy = ref(false), sending = ref(false), responding = ref(null), failure = ref(false);
const query = computed(() => search.value.trim().toLocaleLowerCase());
const friends = computed(() => (data.value?.friends || []).filter(friend =>
  [friend.username, friend.display_name].some(value => value.toLocaleLowerCase().includes(query.value)))
  .sort((a,b) => Number(b.online)-Number(a.online)));
let controller, generation = 0, presencePending = false;
watch(friendsOpen, opened => {
  controller?.abort();
  generation++;
  if (opened && account.value) {
    data.value = null; search.value = ''; username.value = ''; sending.value = false;
    responding.value = null; busy.value = true; failure.value = false;
    requestPanel.value.open = false;
    drawer.value.showModal();
    void refresh();
  } else drawer.value?.close();
});
watch(() => account.value?.id, () => { friendCount.value = null; void pulse(); }, {immediate:true});
async function refresh(background = false) {
  controller?.abort();
  const call = controller = new AbortController();
  try {
    const result = await api('/friends', {signal:call.signal});
    if (call.signal.aborted || !friendsOpen.value) return;
    friendCount.value = result.friends.length;
    if (background && data.value) {
      if (list.value?.contains(document.activeElement)) result.friends = data.value.friends;
      if (requests.value?.contains(document.activeElement)) {
        result.incoming = data.value.incoming; result.outgoing = data.value.outgoing;
      }
    }
    data.value = result;
  } catch (error) {
    if (!background && !call.signal.aborted && friendsOpen.value) {
      failure.value = !data.value;
      showNotice(error.message);
    }
  } finally { if (!call.signal.aborted) busy.value = false; }
}
async function send() {
  if (sending.value) return;
  const ticket = generation;
  sending.value = true;
  try {
    await api('/friends/requests', {method:'POST',body:{username:username.value}});
    if (ticket !== generation || !friendsOpen.value) return;
    username.value = '';
    await refresh();
    if (ticket === generation && friendsOpen.value) showNotice('Friend request sent.',true);
  } catch (error) { if (ticket === generation && friendsOpen.value) showNotice(error.message); }
  finally { if (ticket === generation) sending.value = false; }
}
async function respond(from, decision) {
  if (responding.value) return;
  const ticket = generation;
  responding.value = from + ':' + decision;
  try {
    await api('/friends/requests/' + encodeURIComponent(from) + '/respond', {method:'POST',body:{decision}});
    if (ticket === generation && friendsOpen.value) await refresh();
  } catch (error) { if (ticket === generation && friendsOpen.value) showNotice(error.message); }
  finally { if (ticket === generation) responding.value = null; }
}
async function pulse() {
  if (!account.value || document.hidden || presencePending) return;
  presencePending = true;
  try { await api('/friends/presence', {method:'POST'}); }
  catch { /* Presence failures should not interrupt study. */ }
  finally { presencePending = false; }
}
useEvent(document,'visibilitychange',pulse);
const presence = setInterval(pulse,45000);
const background = setInterval(() => {
  if (friendsOpen.value && data.value && !document.hidden && !responding.value && !sending.value) void refresh(true);
},15000);
onScopeDispose(() => { controller?.abort(); clearInterval(presence); clearInterval(background); });
</script>
<template>
  <Teleport to="body">
    <dialog id="friends-drawer" ref="drawer" v-button-feedback aria-labelledby="friends-heading" @close="closeFriends" @click.self="closeFriends">
      <div class="friends-content">
        <div class="drawer-heading"><h2 id="friends-heading">Friends</h2><button type="button" class="secondary flat-button" aria-label="Close friends" @click="closeFriends">×</button></div>
        <label class="sr-only" for="friend-search">Search friends</label>
        <input id="friend-search" v-model="search" type="search" placeholder="Search friends…" autocomplete="off" autofocus>
        <div id="friend-list" ref="list" :aria-busy="busy">
          <template v-if="data">
            <details v-for="friend in friends" :key="friend.username" class="friend-row" :data-friend="friend.username" name="friend-actions">
              <summary><span class="friend-avatar" aria-hidden="true">{{ Array.from(friend.display_name.trim())[0]?.toUpperCase() || '?' }}<span class="presence-dot" :class="friend.online ? 'online' : 'offline'"></span></span>
                <span class="friend-name"><strong>{{ friend.display_name }}</strong><small>{{ friend.online ? 'Online' : 'Offline' }}</small></span><span class="friend-chevron" aria-hidden="true">⌄</span></summary>
              <div class="friend-actions"><a class="button secondary small flat-button" :href="profilePath(friend.username)" @click="closeFriends">View Profile</a>
                <button class="secondary small flat-button" type="button" disabled>Invite for a study session</button></div>
            </details>
            <p v-if="!friends.length" class="friend-empty">{{ query ? 'No friends match your search.' : 'No friends yet. Send a request by username.' }}</p>
          </template>
          <template v-else>{{ failure ? 'Couldn’t load your friends.' : 'Loading friends…' }}</template>
        </div>
        <details class="friend-requests" ref="requestPanel"><summary id="friend-requests-label">Friend requests{{ data?.incoming.length ? ' (' + data.incoming.length + ')' : '' }}</summary>
          <form id="add-friend" @submit.prevent="send"><label for="friend-username">Add by username</label>
            <div class="friend-request-form"><input id="friend-username" v-model="username" name="username" required minlength="3" maxlength="32" pattern="[A-Za-z0-9_]{3,32}" autocomplete="off" placeholder="Username">
            <button type="submit" class="small" :disabled="sending">Send request</button></div></form>
          <div id="friend-request-list" ref="requests">
            <div v-for="person in data?.incoming" :key="person.username" class="friend-request"><strong>{{ person.display_name }}</strong> <small>@{{ person.username }}</small>
              <div class="actions"><button class="small" type="button" :disabled="responding === person.username + ':accept'" @click="respond(person.username,'accept')">Accept</button>
              <button class="secondary flat-button small" type="button" :disabled="responding === person.username + ':decline'" @click="respond(person.username,'decline')">Decline</button></div></div>
            <p v-for="person in data?.outgoing" :key="'pending-' + person.username" class="friend-request">Pending · @{{ person.username }}</p>
          </div>
        </details>
      </div>
    </dialog>
  </Teleport>
</template>
