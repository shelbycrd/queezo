<script setup>
import {computed, ref, watch} from 'vue';
import {useRoute, useRouter} from 'vue-router';
import {api} from '../../js/api.js';
import {backIcon, plural} from '../services/format.js';
import {avatarUrl} from '../services/profiles.js';
import {useLifetime} from '../composables/lifecycle.js';
import {SEARCH_TABS, normalizePage, normalizeQuery, normalizeTab, searchLocation, searchRequestPath} from '../services/global-search.js';
import LoadingSkeleton from '../components/LoadingSkeleton.vue';

const route = useRoute(), router = useRouter(), lifetime = useLifetime();
const query = computed(() => normalizeQuery(route.query.q));
const tab = computed(() => normalizeTab(route.query.tab));
const page = computed(() => normalizePage(route.query.page));
const data = ref(null), loading = ref(false), error = ref('');
let controller, serial = 0;

async function load() {
  controller?.abort();
  data.value = null; error.value = '';
  if (!query.value) { loading.value = false; return; }
  const mine = ++serial;
  controller = new AbortController();
  lifetime.signal.addEventListener('abort', () => controller.abort(), {once:true});
  loading.value = true;
  try {
    const result = await api(searchRequestPath(query.value, tab.value, page.value), {signal:controller.signal});
    if (mine === serial) data.value = result;
  } catch (failure) {
    if (mine === serial && !controller.signal.aborted) error.value = failure.message;
  } finally { if (mine === serial) loading.value = false; }
}
watch([query, tab, page], load, {immediate:true});

// Tabs and pages replace the entry, so the Back button still returns to the page the search started from.
const show = (nextTab, nextPage = 1) => router.replace(searchLocation(query.value, nextTab, nextPage));
function goBack() {
  if (window.history.state?.back) router.back();
  else void router.push('/home');
}
const sections = computed(() => data.value ? [
  {key:'public_decks', label:'Public Decks', tab:'public', ...data.value.public_decks},
  {key:'my_decks', label:'My Decks', tab:'mine', ...data.value.my_decks},
  {key:'users', label:'Users', tab:'users', ...data.value.users},
].filter(section => tab.value === 'all' || section.tab === tab.value) : []);
const total = computed(() => sections.value.reduce((sum, section) => sum + section.items.length, 0));
const current = computed(() => sections.value[0]);
const byline = item => item.scope === 'mine' ? item.visibility[0].toUpperCase() + item.visibility.slice(1)
  : item.owner ? 'by ' + (item.owner.display_name || item.owner.username) : 'Public deck';
</script>

<template>
  <div class="search-page">
    <div class="page-heading">
      <div class="search-heading">
        <button type="button" class="secondary flat-button search-back" aria-label="Go back" @click="goBack"><span aria-hidden="true" v-html="backIcon"></span> Back</button>
        <h1>Search<template v-if="query">: <span class="search-term">“{{ query }}”</span></template></h1>
      </div>
    </div>

    <div class="search-tabs" role="tablist" aria-label="Search results">
      <button v-for="item in SEARCH_TABS" :key="item.value" type="button" role="tab" class="flat-button" :class="{active:tab === item.value}" :aria-selected="tab === item.value" @click="show(item.value)">{{ item.label }}</button>
    </div>

    <div class="search-results" role="tabpanel" :aria-busy="loading">
      <section v-if="!query" class="panel search-state"><h2>Search Queezo</h2><p class="muted">Find public decks, your own decks, and other students’ profiles.</p></section>
      <LoadingSkeleton v-else-if="loading" variant="results" :count="4" label="Searching…"/>
      <section v-else-if="error" class="panel search-state" role="alert"><h2>Search didn’t work</h2><p>{{ error }}</p><button type="button" class="secondary flat-button" @click="load">Try again</button></section>
      <section v-else-if="data && !total" class="panel search-state" role="status"><h2>No results</h2><p class="muted">Nothing matched “{{ query }}”. Try a different word or check the spelling.</p></section>

      <template v-else-if="data">
        <section v-for="section in sections.filter(item => item.items.length)" :key="section.key" class="search-section" :aria-label="section.label">
          <div class="section-heading"><h2>{{ section.label }}</h2><button v-if="tab === 'all' && section.has_more" type="button" class="link-button" @click="show(section.tab)">See all</button></div>
          <ul class="search-list">
            <li v-for="item in section.items" :key="item.ref">
              <a class="search-result" :href="item.path">
                <img v-if="item.kind === 'user'" class="search-avatar" :src="avatarUrl(item.avatar)" alt="" width="44" height="44">
                <span v-else class="search-deck-icon" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="6" y="6" width="15" height="15" rx="3"/><path d="M17 3H6a3 3 0 0 0-3 3v11M10 11h7m-7 4h4"/></svg></span>
                <span class="search-text">
                  <strong>{{ item.kind === 'user' ? item.display_name || item.username : item.title }}</strong>
                  <small v-if="item.kind === 'user'">@{{ item.username }}</small>
                  <small v-else>{{ plural(item.card_count, 'flashcard') }} · {{ byline(item) }}</small>
                </span>
              </a>
            </li>
          </ul>
        </section>
        <nav v-if="tab !== 'all' && (page > 1 || current?.has_more)" class="search-pager" aria-label="Result pages">
          <button type="button" class="secondary flat-button" :disabled="page <= 1" @click="show(tab, page - 1)">Previous</button>
          <span class="muted">Page {{ page }}</span>
          <button type="button" class="secondary flat-button" :disabled="!current?.has_more" @click="show(tab, page + 1)">Next</button>
        </nav>
      </template>
    </div>
  </div>
</template>
