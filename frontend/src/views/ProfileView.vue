<script setup>
import {computed, ref, watch} from 'vue';
import {api} from '../../js/api.js';
import {useEvent, useResource} from '../composables/lifecycle.js';
import {account, updateAccountProfile} from '../services/session.js';
import {showNotice} from '../services/notice.js';
import {avatarUrl, deckPagePath, profileApi, profilePath} from '../services/profiles.js';
import {buttonFeedback as vButtonFeedback} from '../components/ButtonFeedback.js';
import CopyButton from '../components/CopyButton.vue';
import DeckTile from '../components/DeckTile.vue';
import ProfileEditor from '../components/ProfileEditor.vue';
import ReportProfileDialog from '../components/ReportProfileDialog.vue';

const props = defineProps({username:String});
const path = props.username ? profileApi(props.username) : '/profiles/me';
const {data:profile, error, active, signal} = useResource(signal => api(path,{signal}));
const editing = ref(''), reporting = ref(false), shareDialog = ref();
const friendshipPending = ref(false), friendshipMenu = ref();
useEvent(document,'click', event => {
  const menu = friendshipMenu.value;
  if (menu?.open && !menu.contains(event.target)) menu.open = false;
});
function closeFriendshipMenu() {
  friendshipMenu.value.open = false;
  friendshipMenu.value.querySelector('summary').focus();
}
async function changeFriendship() {
  const {username, friendship} = profile.value;
  if (friendshipPending.value || !['none','incoming','friends'].includes(friendship)) return;
  const target = '/friends/' + encodeURIComponent(username);
  friendshipPending.value = true;
  try {
    if (friendship === 'friends') {
      await api(target,{method:'DELETE'});
    } else if (friendship === 'incoming') {
      await api('/friends/requests/' + encodeURIComponent(username) + '/respond',{method:'POST',body:{decision:'accept'}});
    } else {
      await api('/friends/requests',{method:'POST',body:{username}});
    }
    if (active()) profile.value = {...profile.value,friendship:friendship === 'friends' ? 'none' : friendship === 'incoming' ? 'friends' : 'outgoing'};
  } catch (failure) {
    if (!active()) return;
    if ([0,404,409].includes(failure.status)) {
      try {
        const latest = await api(path,{signal});
        if (!active()) return;
        profile.value = latest;
        if (failure.status === 409 && latest.friendship && latest.friendship !== friendship) return;
      } catch { /* Preserve the original error. */ }
    }
    if (active()) showNotice(failure.message);
  } finally {
    friendshipPending.value = false;
  }
}
const input = ref(''), q = ref(''), sort = ref('newest'), page = ref(1), reload = ref(0);
const decks = ref(null), deckError = ref(''), loading = ref(false);
const shareLink = computed(() => new URL(profilePath(profile.value.username),location.origin).href);
const joined = computed(() => new Date(profile.value.joined_at).toLocaleDateString(undefined,{month:'long',year:'numeric',timeZone:'UTC'}));
watch([() => profile.value?.username,q,sort,page,reload], async ([username],_,onCleanup) => {
  if (!username) return;
  const controller = new AbortController();
  onCleanup(() => controller.abort());
  loading.value = true; deckError.value = ''; decks.value = null;
  try {
    const data = await api(deckPagePath(username,{q:q.value,sort:sort.value,page:page.value}),{signal:controller.signal});
    if (!controller.signal.aborted) decks.value = data;
  } catch (failure) {
    if (!controller.signal.aborted) deckError.value = failure.message;
  } finally {
    if (!controller.signal.aborted) loading.value = false;
  }
}, {immediate:true});
function search() { page.value = 1; q.value = input.value.trim(); }
function saved(data) {
  profile.value = data;
  updateAccountProfile(data);
  if (editing.value === 'avatar') return;
  page.value = 1;
  reload.value++;
}
</script>
<template>
  <div class="profile-page">
    <section v-if="!profile && error" class="panel">
      <h1>{{ error === 'Profile not found.' ? 'Profile unavailable' : 'Couldn’t load this profile' }}</h1>
      <p class="muted">{{ error === 'Profile not found.' ? 'This profile may be private or the link may be incorrect.' : error }}</p>
      <a href="/#/dashboard" class="button secondary flat-button">Back to Queezo</a>
    </section>
    <p v-else-if="!profile" class="muted" role="status">Loading profile…</p>
    <template v-else>
      <section class="panel profile-card profile-header" aria-label="Profile">
        <div class="profile-picture-wrap">
          <img class="profile-avatar profile-picture" :src="avatarUrl(profile.avatar)" alt="" width="138" height="138">
          <button v-if="profile.is_owner" type="button" class="secondary flat-button profile-picture-edit" aria-label="Change profile picture" title="Change profile picture" @click="editing = 'avatar'">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m14 6 4 4M4 20l4.5-1 11-11a2.8 2.8 0 0 0-4-4l-11 11L4 20Z"/></svg>
          </button>
        </div>
        <div class="profile-identity"><h1>{{ profile.display_name }}</h1><p class="profile-username">@{{ profile.username }}</p><p class="muted profile-joined">Joined {{ joined }}</p></div>
        <div class="profile-actions">
          <button v-if="profile.is_owner" type="button" @click="editing = 'profile'">Edit Profile</button>
          <button type="button" class="secondary flat-button" @click="shareDialog.showModal()">Share Profile</button>
          <button v-if="account && !profile.is_owner" type="button" class="secondary flat-button" @click="reporting = true">Report Profile</button>
          <a v-if="profile.is_owner" href="/#/people" class="button secondary flat-button">Find profiles</a>
          <a v-else-if="!account" href="/#/login" class="button">Add Friend</a>
          <details v-else-if="profile.friendship === 'friends'" ref="friendshipMenu" class="deck-actions profile-friendship" @keydown.esc.stop="closeFriendshipMenu">
            <summary class="button secondary flat-button">Friends ✔</summary>
            <div class="deck-actions-list"><button type="button" class="danger small flat-button" :disabled="friendshipPending" @click="changeFriendship">Unfriend</button></div>
          </details>
          <button v-else-if="profile.friendship === 'outgoing'" type="button" class="secondary flat-button profile-request-sent" disabled>Request Sent</button>
          <button v-else-if="profile.friendship === 'none' || profile.friendship === 'incoming'" type="button" :disabled="friendshipPending" @click="changeFriendship">{{ profile.friendship === 'incoming' ? 'Accept Request' : 'Add Friend' }}</button>
          <span v-else class="muted" role="status">Friendship status unavailable</span>
        </div>
      </section>
      <div class="profile-layout">
        <aside class="profile-sidebar">
          <section class="panel"><h2>About Me</h2><p v-if="profile.bio" class="profile-bio">{{ profile.bio }}</p><p v-else class="muted">No bio yet.</p></section>
          <section class="panel"><h2>Interests</h2><ul v-if="profile.interest_tags.length" class="profile-tags"><li v-for="tag in profile.interest_tags" :key="tag" class="badge">{{ tag }}</li></ul><p v-else class="muted">No interests listed.</p></section>
        </aside>
        <div class="profile-main">
          <section v-if="profile.featured_deck" class="profile-featured">
            <div class="section-heading"><h2>Featured deck</h2></div>
            <DeckTile :deck="profile.featured_deck" shared/>
          </section>
          <section class="profile-public">
            <div class="section-heading"><h2>Public Decks</h2></div>
            <div class="profile-filters">
              <form role="search" class="new-deck-form" @submit.prevent="search"><div><label for="profile-deck-search">Search decks</label><input id="profile-deck-search" v-model="input" type="search" maxlength="120" placeholder="Search by title…" @search="search"></div><button type="submit" class="secondary flat-button">Search</button></form>
              <div><label for="profile-deck-sort">Sort decks</label><select id="profile-deck-sort" v-model="sort" @change="page = 1"><option value="newest">Newest</option><option value="oldest">Oldest</option><option value="alphabetical">Alphabetical</option></select></div>
            </div>
            <p v-if="loading" class="muted" role="status">Loading public decks…</p>
            <div v-else-if="deckError" class="panel" role="status"><p>{{ deckError }}</p><button type="button" class="secondary flat-button" @click="reload++">Retry</button></div>
            <div v-else-if="decks?.items.length" class="deck-grid profile-deck-grid"><DeckTile v-for="deck in decks.items" :key="deck.share_token" :deck="deck" shared/></div>
            <div v-else-if="decks" class="empty"><p>{{ q ? 'No public decks match your search.' : profile.featured_deck ? 'No other public decks yet.' : 'No public decks yet.' }}</p></div>
            <nav v-if="page > 1 || decks?.has_more" aria-label="Public deck pages" class="saved-card-pages">
              <button type="button" class="secondary small flat-button" :disabled="page === 1 || loading" @click="page--">Previous</button><span aria-live="polite">Page {{ page }}</span><button type="button" class="secondary small flat-button" :disabled="!decks?.has_more || loading" @click="page++">Next</button>
            </nav>
          </section>
        </div>
      </div>
      <ProfileEditor v-if="editing" :profile="profile" :avatar-only="editing === 'avatar'" @saved="saved" @close="editing = ''"/>
      <ReportProfileDialog v-if="reporting" :username="profile.username" @close="reporting = false"/>
      <Teleport to="body">
        <dialog ref="shareDialog" v-button-feedback class="profile-dialog" aria-labelledby="share-profile-title">
          <div class="dialog-heading"><h2 id="share-profile-title">Share Profile</h2><button type="button" class="secondary small flat-button" aria-label="Close share profile" @click="shareDialog.close()">×</button></div>
          <p v-if="profile.visibility === 'private'" class="hint">Your profile is private. Other people won’t be able to open this link.</p>
          <label for="profile-share-link">Profile link</label><input id="profile-share-link" :value="shareLink" readonly>
          <div class="actions"><CopyButton :value="shareLink">Copy Link</CopyButton></div>
        </dialog>
      </Teleport>
    </template>
  </div>
</template>
