<script setup>
import {computed, nextTick, ref, watch} from 'vue';
import {useRoute, useRouter} from 'vue-router';
import {api} from '../../js/api.js';
import {useEvent, useLifetime} from '../composables/lifecycle.js';
import {account} from '../services/session.js';
import {avatarUrl} from '../services/profiles.js';
import {browserStorage, clearRecents, readRecents, recordVisit, visitRefForRoute} from '../services/recent-visits.js';
import {MAX_QUERY, normalizeQuery, recentRequestPath, searchLocation} from '../services/global-search.js';
import LoadingSkeleton from './LoadingSkeleton.vue';

const route = useRoute(), router = useRouter(), {signal} = useLifetime();
const root = ref(), input = ref();
const query = ref(''), open = ref(false), expanded = ref(false);
const recents = ref([]), loading = ref(false), failed = ref(false), active = ref(-1);
let request = 0;
const userId = computed(() => account.value?.id ?? null);
const showRecents = computed(() => open.value && !query.value.trim());

// Remember the decks and profiles this account opens (references only; see recent-visits.js).
watch(() => route.fullPath, () => {
  const visit = visitRefForRoute(route);
  if (visit && userId.value != null && browserStorage()) recordVisit(browserStorage(), userId.value, visit);
}, {immediate:true});
// Keep the box in step with the results page, and empty it elsewhere.
watch(() => [route.name, route.query.q], () => { query.value = route.name === 'search' ? normalizeQuery(route.query.q) : ''; }, {immediate:true});
watch(userId, () => { recents.value = []; close(); });

async function loadRecents() {
  const storage = browserStorage(), refs = storage ? readRecents(storage, userId.value) : [];
  const mine = ++request;
  failed.value = false;
  if (!refs.length) { recents.value = []; loading.value = false; return; }
  loading.value = true;
  try {
    const data = await api(recentRequestPath(refs), {signal});
    if (mine === request) recents.value = data.items;
  } catch (error) {
    if (mine === request && !signal.aborted) { failed.value = true; recents.value = []; }
  } finally { if (mine === request) loading.value = false; }
}
function show() {
  if (open.value) return;
  open.value = true; active.value = -1;
  void loadRecents();
}
function close() { open.value = false; active.value = -1; request++; }
function collapse() { close(); expanded.value = false; }
async function expand() {
  expanded.value = true;
  await nextTick();
  input.value?.focus();
}
function submit() {
  const term = normalizeQuery(query.value);
  if (active.value >= 0 && showRecents.value && recents.value[active.value]) return go(recents.value[active.value]);
  if (!term) return;
  query.value = term;
  close(); input.value?.blur(); expanded.value = false;
  void router.push(searchLocation(term));
}
function go(item) { collapse(); void router.push(item.path); }
function typed() {
  if (query.value.trim()) close();
  else show();
}
function clear() {
  query.value = '';
  input.value?.focus();
  show();
}
function forget() {
  if (userId.value != null && browserStorage()) clearRecents(browserStorage(), userId.value);
  recents.value = []; active.value = -1;
}
function step(delta) {
  if (!showRecents.value) show();
  if (!recents.value.length) return;
  active.value = (active.value + delta + recents.value.length) % recents.value.length;
}
function escape() {
  if (open.value || expanded.value) { collapse(); input.value?.blur(); }
}
useEvent(document, 'click', event => { if (!root.value?.contains(event.target)) collapse(); });
const subtitle = item => item.kind === 'user' ? '@' + item.username
  : item.scope === 'mine' ? `Your deck · ${item.visibility}` : item.visibility === 'unlisted' ? 'Shared deck' : 'Public deck';
const label = item => item.kind === 'user' ? item.display_name || item.username : item.title;
</script>

<template>
  <div ref="root" class="global-search" :class="{expanded}" role="search" @focusout="event => { if (!root.contains(event.relatedTarget)) close(); }">
    <button type="button" class="topbar-icon secondary flat-button search-toggle" aria-label="Open search" :aria-expanded="expanded" @click="expand">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" aria-hidden="true"><circle cx="11" cy="11" r="6.5"/><path d="m16 16 4.5 4.5"/></svg>
    </button>
    <form class="search-field" @submit.prevent="submit">
      <button type="button" class="search-collapse flat-button" aria-label="Close search" @click="collapse"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m14 5-7 7 7 7"/></svg></button>
      <svg class="search-glyph" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" aria-hidden="true"><circle cx="11" cy="11" r="6.5"/><path d="m16 16 4.5 4.5"/></svg>
      <input ref="input" v-model="query" type="search" name="q" autocomplete="off" spellcheck="false" :maxlength="MAX_QUERY * 2" placeholder="Search decks and people" aria-label="Search decks and people"
        role="combobox" aria-autocomplete="list" aria-haspopup="listbox" aria-controls="search-recents" :aria-expanded="showRecents" :aria-activedescendant="active >= 0 && showRecents ? 'recent-' + active : undefined"
        @focus="show" @click="show" @input="typed" @keydown.down.prevent="step(1)" @keydown.up.prevent="step(-1)" @keydown.esc.stop="escape">
      <button v-if="query" type="button" class="search-clear flat-button" aria-label="Clear search" @click="clear"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="m6 6 12 12M18 6 6 18"/></svg></button>
    </form>
    <div v-show="showRecents" id="search-recents" class="search-dropdown" @mousedown.prevent>
      <div class="search-dropdown-heading"><strong id="recent-heading">Recent</strong><button v-if="recents.length" type="button" class="link-button" @click="forget">Clear</button></div>
      <LoadingSkeleton v-if="loading" variant="results" :count="3" label="Loading recent visits…"/>
      <p v-else-if="failed" class="muted search-note" role="alert">Couldn’t load your recent visits.</p>
      <ul v-else-if="recents.length" role="listbox" aria-labelledby="recent-heading">
        <li v-for="(item, index) in recents" :id="'recent-' + index" :key="item.ref" role="option" :aria-selected="active === index">
          <a :href="item.path" :class="{current:active === index}" @click.prevent="go(item)">
            <img v-if="item.kind === 'user'" class="search-avatar" :src="avatarUrl(item.avatar)" alt="" width="32" height="32">
            <span v-else class="search-deck-icon" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="6" y="6" width="15" height="15" rx="3"/><path d="M17 3H6a3 3 0 0 0-3 3v11M10 11h7m-7 4h4"/></svg></span>
            <span class="search-text"><strong>{{ label(item) }}</strong><small>{{ subtitle(item) }}</small></span>
          </a>
        </li>
      </ul>
      <p v-else class="muted search-note">Decks and profiles you open will show up here.</p>
    </div>
  </div>
</template>
