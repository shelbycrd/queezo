<script setup>
import {computed, nextTick, ref, watch} from 'vue';
import {useRouter} from 'vue-router';
import {api} from '../../js/api.js';
import {icon} from '../../js/icons.js';
import {plural} from '../services/format.js';
import {showNotice} from '../services/notice.js';
import {useResource} from '../composables/lifecycle.js';
import ResourceState from '../components/ResourceState.vue';
import DeckTile from '../components/DeckTile.vue';
import VisibilityOptions from '../components/VisibilityOptions.vue';

const props = defineProps({create:String});
const router = useRouter();
const {data:items,error,active} = useResource(signal => api('/decks',{signal}));
const search = ref(''), searchBox = ref(), sort = ref('new'), dialog = ref(), titleInput = ref();
const title = ref(''), visibility = ref('private'), pending = ref(false);
const query = computed(() => search.value.trim().toLocaleLowerCase());
const tiles = computed(() => [...(items.value || [])].sort((a,b) => sort.value === 'name' ? a.title.localeCompare(b.title) :
  sort.value === 'cards' ? b.card_count-a.card_count || b.created_at.localeCompare(a.created_at) || b.id-a.id :
  (sort.value === 'old' ? 1 : -1)*(a.created_at.localeCompare(b.created_at)||a.id-b.id)));
const matchesQuery = deck => deck.title.toLocaleLowerCase().includes(query.value);
const matches = computed(() => tiles.value.filter(matchesQuery).length);
function openCreate() { dialog.value.showModal(); titleInput.value.focus(); }
watch(items, async value => { if (value && props.create === 'new') { await nextTick(); if (active()) openCreate(); } });
async function submit() {
  if (pending.value) return;
  pending.value = true;
  try {
    const created = await api('/decks',{method:'POST',body:{title:title.value, visibility:visibility.value}});
    if (active()) { dialog.value.close(); await router.push('/deck/' + created.id); }
  } catch (failure) { if (active()) showNotice(failure.message); }
  finally { pending.value = false; }
}
</script>
<template>
  <ResourceState v-if="!items" :error="error" variant="grid"/>
  <template v-else>
    <div class="page-heading"><div><h1>Your Decks</h1></div><span class="deck-total">{{ plural(items.length,'deck') }}</span></div>
    <div class="deck-tools"><form id="deck-search" class="new-deck-form" role="search" @submit.prevent><div><label for="deck-search-input">Search decks</label><input id="deck-search-input" ref="searchBox" v-model="search" type="search" placeholder="Search your decks…" autocomplete="off"></div><button type="submit" class="secondary">Search</button></form><button id="open-create-deck" type="button" @click="openCreate"><span v-html="icon('plus')"></span> Create Deck</button></div>
    <dialog id="create-deck-dialog" class="create-deck-dialog" ref="dialog"><form id="new-deck" @submit.prevent="submit"><h2>Create a deck</h2><label for="deck-title">Deck title</label><input id="deck-title" ref="titleInput" v-model="title" name="title" required maxlength="120" autocomplete="off"><label for="deck-visibility">Visibility</label><select id="deck-visibility" name="visibility" v-model="visibility"><VisibilityOptions/></select><div class="actions"><button id="cancel-create-deck" type="button" class="secondary" :disabled="pending" @click="dialog.close()">Cancel</button><button type="submit" :disabled="pending">Create Deck</button></div></form></dialog>
    <div class="collection-tools"><label for="deck-sort">Sort decks <select id="deck-sort" v-model="sort"><option value="new">Newest first</option><option value="old">Oldest first</option><option value="name">Title A–Z</option><option value="cards">Most cards</option></select></label><span id="deck-matches" role="status">{{ matches }} of {{ items.length }} decks</span><button id="clear-deck-search" class="secondary small flat-button" type="button" :hidden="!query" @click="search = ''; searchBox.focus()">Clear search</button></div>
    <p v-if="items.length && !matches" id="deck-search-empty" class="empty">No decks match your search.</p>
    <div v-if="items.length" class="deck-grid"><DeckTile v-for="deck in tiles" :key="deck.id" :deck="deck" :hidden="!matchesQuery(deck)"/></div>
    <div v-else class="empty"><h2>Something worth remembering?</h2><p class="muted">Create your first deck, then add your questions and answers.</p></div>
  </template>
</template>
