<script setup>
import {computed, onScopeDispose, ref, watch} from 'vue';
import {api} from '../../js/api.js';
import {icon} from '../../js/icons.js';
import {account} from '../services/session.js';
import {avatarUrl, profilePath} from '../services/profiles.js';
import {friendsOpen, openFriends} from '../services/friends.js';
import {greeting, sortFriends} from '../services/home.js';
import {useNow} from '../composables/clock.js';
import {useLifetime, useResource} from '../composables/lifecycle.js';
import DeckTile from '../components/DeckTile.vue';
import HomeSchedule from '../components/HomeSchedule.vue';
import LoadingSkeleton from '../components/LoadingSkeleton.vue';
import ResourceState from '../components/ResourceState.vue';

const {data, error} = useResource(signal => Promise.all(['/dashboard','/dashboard/activity','/community/decks'].map(path => api(path,{signal})))
  .then(([stats,activity,recent]) => ({stats,activity,recent:recent.slice(0,20)})));
const {signal, active} = useLifetime();

// Greeting follows the browser's local clock, refreshed on every minute boundary.
const now = useNow();
const name = computed(() => account.value?.display_name || account.value?.username || 'there');
const hello = computed(() => greeting(now.value) + ', ' + name.value + '!');

const days = computed(() => {
  const activity = data.value.activity, todayKey = new Date(activity.today + 'T00:00:00Z');
  return Array.from({length:7}, (_, i) => {
    const date = new Date(todayKey);
    date.setUTCDate(date.getUTCDate() - 6 + i);
    const key = date.toISOString().slice(0,10);
    return {key, label:date.toLocaleDateString('en',{weekday:'narrow',timeZone:'UTC'}), studied:activity.active_days.includes(key)};
  });
});

// Explore Public Decks: search runs only on Enter; the X clears the field.
const query = ref(''), applied = ref(''), searching = ref(false), results = ref(null), searchInput = ref();
const decks = computed(() => results.value ?? data.value?.recent ?? []);
let searchController;
async function search() {
  const term = query.value.trim();
  searchController?.abort();
  if (!term) { applied.value = ''; results.value = null; searching.value = false; return; }
  const call = searchController = new AbortController();
  signal.addEventListener('abort', () => call.abort(), {once:true});
  searching.value = true;
  try {
    const found = await api('/community/decks?q=' + encodeURIComponent(term), {signal:call.signal});
    if (call.signal.aborted || !active()) return;
    applied.value = term; results.value = found;
  } catch (failure) {
    if (!call.signal.aborted && active()) { applied.value = term; results.value = []; searchError.value = failure.message; }
  } finally { if (searchController === call) searching.value = false; }
}
const searchError = ref('');
function clearSearch() {
  query.value = ''; searchError.value = '';
  if (applied.value || searching.value) void search(); // Return to the newest public decks.
  searchInput.value?.focus();
}
watch(query, () => { searchError.value = ''; });

const track = ref(), previous = ref(false), next = ref(false);
const observer = new ResizeObserver(update);
watch(track, element => { observer.disconnect(); if (element) observer.observe(element); update(); });
watch(decks, () => queueMicrotask(update));
onScopeDispose(() => { observer.disconnect(); searchController?.abort(); });
function update() {
  const element = track.value;
  previous.value = Boolean(element && element.scrollLeft > 1);
  next.value = Boolean(element && element.scrollLeft + element.clientWidth < element.scrollWidth - 2);
}
function scroll(left) {
  track.value?.scrollBy({left,behavior:matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth'});
}

// Friends widget: one read on open, refreshed when the Friends drawer closes. No polling.
const friends = ref(null), friendsFailed = ref(false);
async function loadFriends() {
  try {
    const result = await api('/friends', {signal});
    if (active()) { friends.value = sortFriends(result.friends); friendsFailed.value = false; }
  } catch { if (active() && !friends.value) friendsFailed.value = true; }
}
void loadFriends();
watch(friendsOpen, open => { if (!open) void loadFriends(); });
</script>
<template>
  <ResourceState v-if="!data" :error="error" variant="home"/>
  <div v-else class="home-dashboard">
    <div class="home-main">
      <h1 class="home-greeting">{{ hello }}</h1>

      <HomeSchedule/>

      <section class="recent-section explore-section" aria-labelledby="explore-heading">
        <div class="section-heading explore-heading">
          <h2 id="explore-heading">Explore Public Decks</h2>
          <form class="explore-search" role="search" @submit.prevent="search">
            <label class="sr-only" for="explore-search">Search public decks</label>
            <input id="explore-search" ref="searchInput" v-model="query" type="search" maxlength="120" autocomplete="off"
              placeholder="Search public decks…" enterkeyhint="search" aria-describedby="explore-search-hint">
            <span id="explore-search-hint" class="sr-only">Press Enter to search.</span>
            <button v-if="query" type="button" class="explore-clear" aria-label="Clear search" @click="clearSearch">×</button>
          </form>
          <div class="carousel-controls"><button type="button" id="recent-prev" class="icon-button secondary" aria-label="Previous decks" :disabled="!previous" @click="scroll(-300)">←</button><button type="button" id="recent-next" class="icon-button secondary" aria-label="Next decks" :disabled="!next" @click="scroll(300)">→</button></div>
        </div>
        <p class="sr-only" role="status" aria-live="polite">{{ searching ? 'Searching public decks…' : applied ? decks.length + ' public decks match ' + applied : '' }}</p>
        <LoadingSkeleton v-if="searching" variant="grid" :count="3" label="Searching public decks…"/>
        <div v-else-if="decks.length" class="recent-track" id="recent-track" ref="track" tabindex="0" :aria-label="applied ? 'Public decks matching ' + applied : 'Public decks, newest first'" @scroll="update"><DeckTile v-for="deck in decks" :key="deck.share_token" :deck="deck" shared/></div>
        <div v-else-if="applied" class="empty"><div class="empty-icon" v-html="icon('cards')"></div><h3>{{ searchError || 'No public decks match “' + applied + '”.' }}</h3><p class="muted">Try a different title.</p></div>
        <div v-else class="empty"><div class="empty-icon" v-html="icon('cards')"></div><h3>No public decks yet.</h3><p class="muted">Create a deck and choose Public to share it here.</p><a class="button secondary" href="/flashcards">Create a deck</a></div>
      </section>
    </div>

    <aside class="home-widgets" aria-label="Study widgets">
      <section class="panel streak-panel" aria-labelledby="streak-heading"><div class="section-heading"><h2 id="streak-heading">Study Streak</h2></div><div class="streak-number">{{ data.activity.study_streak }}<span> day{{ data.activity.study_streak === 1 ? '' : 's' }} in a row</span></div><p class="muted">{{ data.activity.active_today ? 'You made time to learn today. Keep it going!' : 'A flashcard review or finished pomodoro keeps your streak going.' }}</p>
        <div class="study-week"><div v-for="item in days" :key="item.key" class="week-day" :class="{studied:item.studied}"><span>{{ item.label }}</span><span class="day-dot" role="img" :aria-label="item.key + ': ' + (item.studied ? 'studied' : 'no study recorded')"><span v-if="item.studied" v-html="icon('book')"></span><template v-else>·</template></span></div></div>
        <div class="home-counts"><span><strong>{{ data.stats.deck_count }}</strong> decks</span><span><strong>{{ data.stats.card_count }}</strong> flashcards</span></div>
      </section>

      <section class="panel friends-panel home-friends" aria-labelledby="home-friends-heading">
        <div class="section-heading"><h2 id="home-friends-heading">Friends</h2><button type="button" id="home-friends" class="secondary small flat-button" @click="openFriends">Manage</button></div>
        <LoadingSkeleton v-if="!friends && !friendsFailed" variant="list" :count="3" label="Loading friends…"/>
        <p v-else-if="friendsFailed" class="muted">Couldn’t load your friends.</p>
        <ul v-else-if="friends.length" class="home-friend-list">
          <li v-for="friend in friends" :key="friend.username"><a :href="profilePath(friend.username)">
            <span class="friend-avatar" aria-hidden="true"><img :src="avatarUrl(friend.avatar)" alt="" width="32" height="32"><span class="presence-dot" :class="friend.online ? 'online' : 'offline'"></span></span>
            <span class="home-friend-name"><strong>{{ friend.display_name }}</strong><small>{{ friend.online ? 'Online' : 'Offline' }}</small></span></a></li>
        </ul>
        <p v-else class="muted">No friends yet. <button type="button" class="link-button" @click="openFriends">Add a friend</button></p>
      </section>
    </aside>
  </div>
</template>
