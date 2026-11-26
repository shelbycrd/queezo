<script setup>
import {computed, nextTick, onScopeDispose, reactive, ref, shallowRef, watch} from 'vue';
import {useRouter} from 'vue-router';
import {api} from '../../js/api.js';
import {safeImageUrl} from '../../js/card-content.js';
import {playPageTurn, preparePageSound} from '../../js/audio.js';
import {showNotice} from '../services/notice.js';
import {chooseStudy} from '../services/study-dialog.js';
import {readPhoto} from '../services/photos.js';
import {useResource} from '../composables/lifecycle.js';
import CardContent from '../components/CardContent.vue';
import CopyButton from '../components/CopyButton.vue';
import ResourceState from '../components/ResourceState.vue';
import EditorSide from '../components/EditorSide.vue';
import PreviousSession from '../components/PreviousSession.vue';
import VisibilityOptions from '../components/VisibilityOptions.vue';

const {deckId,cardId,pageNumber,action} = defineProps({deckId:String,cardId:String,pageNumber:String,action:String});
const router = useRouter(), path = '/decks/' + deckId;
const PAGE_SIZE = 20, TEXT_LIMIT = 250;
const deck = ref(), cards = ref([]), editing = shallowRef(null);
const draft = reactive({front:'',back:''}), images = reactive({front:null,back:null});
const visibility = ref('private'), query = ref(''), order = ref('desc');
const page = ref(Number(pageNumber) || 1), editPage = ref(1);
const form = ref(), savedList = ref(), pages = ref(), menu = ref(), saveButton = ref();
const pending = ref(false), savingVisibility = ref(false), deckBusy = ref(false), deleting = ref(false), increments = ref([]);
const {error,active} = useResource(async signal => {
  const [record, fetched] = await Promise.all([path,path+'/cards'].map(url => api(url,{signal})));
  if (signal.aborted) return;
  const card = cardId ? fetched.find(item => item.id === Number(cardId)) : null;
  if (cardId && !card) throw new Error('This card was not found in this deck.');
  cards.value = fetched; editing.value = card;
  for (const side of ['front','back']) {
    draft[side] = card?.[side] || ''; images[side] = safeImageUrl(card?.[side + '_image']) || null;
  }
  if (card) {
    editPage.value = Math.floor((fetched.length - 1 - fetched.indexOf(card)) / PAGE_SIZE) + 1;
    page.value = editPage.value;
  }
  visibility.value = record.visibility || 'private';
  deck.value = record;
  if (card || action === 'add') { await nextTick(); focusQuestion(); }
});

const matches = computed(() => {
  const need = query.value.trim().toLocaleLowerCase();
  return cards.value.filter(card => (card.front + ' ' + card.back).toLocaleLowerCase().includes(need))
    .sort((a,b) => (order.value === 'desc' ? -1 : 1) * (a.id - b.id));
});
const pageCount = computed(() => Math.max(1,Math.ceil(matches.value.length / PAGE_SIZE)));
const saved = computed(() => matches.value.slice((page.value - 1) * PAGE_SIZE,page.value * PAGE_SIZE));
const full = computed(() => cards.value.length >= 150 && !editing.value);
const numberOf = card => cards.value.findIndex(item => item.id === card.id) + 1;
const share = computed(() => deck.value?.share_token ? new URL('/shared/' + deck.value.share_token,location.origin).href : '');
watch(pageCount,value => { page.value = Math.min(page.value,value); }, {immediate:false});
function focusQuestion() { form.value?.elements.front?.focus(); }
function shortcut(event) {
  if ((event.ctrlKey || event.metaKey) && event.key === 'Enter' && !event.isComposing) {
    event.preventDefault();
    if (!saveButton.value.disabled) form.value.requestSubmit(saveButton.value);
  }
}
async function step(amount,event) {
  page.value += amount;
  const button = event.currentTarget;
  await nextTick();
  if (button.disabled) pages.value?.querySelector('button:not(:disabled)')?.focus();
  savedList.value?.scrollIntoView({block:'start'});
}

let photoSequence = 0, photosPending = 0;
async function choosePhoto(side, input) {
  const file = input.files?.[0];
  if (!file || pending.value) return;
  const sequence = ++photoSequence;
  photosPending++;
  try {
    const photo = await readPhoto(file);
    if (active() && sequence === photoSequence) {
      images[side] = photo;
      images[side === 'front' ? 'back' : 'front'] = null;
    }
  } catch (failure) { if (active() && sequence === photoSequence) showNotice(failure.message); }
  finally { photosPending--; input.value = ''; }
}
function removePhoto(side) { ++photoSequence; images[side] = null; }
const incrementTimers = new Set();
let incrementId = 0;
function animateSave() {
  const id = ++incrementId;
  increments.value.push(id);
  const timer = setTimeout(() => {
    increments.value = increments.value.filter(item => item !== id);
    incrementTimers.delete(timer);
  },1000);
  incrementTimers.add(timer);
}
onScopeDispose(() => { for (const timer of incrementTimers) clearTimeout(timer); });

async function submit(event) {
  if (pending.value || deckBusy.value) return;
  if (photosPending) { showNotice('Wait a moment for the photo to finish loading.'); return; }
  const study = event.submitter?.dataset.intent === 'study';
  const shouldSave = editing.value || draft.front.trim() || draft.back.trim() || images.front || images.back || !study;
  if (shouldSave && (!form.value.reportValidity() || !draft.front.trim() || !draft.back.trim())) {
    showNotice('Write both a question and an answer before saving.'); return;
  }
  if (shouldSave && ['front','back'].some(side => draft[side].length > TEXT_LIMIT && draft[side] !== editing.value?.[side])) {
    showNotice('Use 250 characters or fewer for each question and answer.'); return;
  }
  if (shouldSave && full.value) { showNotice('This deck has reached its 150-card limit.'); return; }
  if (!shouldSave && !cards.value.length) { showNotice('Add your first card before starting a study session.'); return; }
  if (!study && !editing.value) preparePageSound();
  pending.value = true;
  try {
    if (shouldSave) {
      const body = {...draft,front_image:images.front,back_image:images.back};
      const card = await api(editing.value ? '/cards/' + editing.value.id : path + '/cards',{method:editing.value ? 'PATCH' : 'POST',body});
      if (!active()) return;
      cards.value = editing.value ? cards.value.map(item => item.id === card.id ? card : item) : [...cards.value,card];
      if (editing.value && !study) { await router.push('/deck/' + deckId + '/page/' + editPage.value); return; }
      if (!editing.value) {
        draft.front = ''; draft.back = ''; images.front = null; images.back = null;
        if (!study) { playPageTurn(); animateSave(); }
      }
      showNotice('');
    }
    if (study) await chooseStudy(deckId);
  } catch (failure) { if (active()) showNotice(failure.message); }
  finally {
    pending.value = false;
    if (!study && !editing.value && active()) { await nextTick(); focusQuestion(); }
  }
}
async function saveVisibility() {
  if (savingVisibility.value || deckBusy.value) return;
  savingVisibility.value = true;
  try {
    const changed = await api(path,{method:'PATCH',body:{visibility:visibility.value}});
    if (active()) { Object.assign(deck.value,changed); showNotice('Visibility saved ✓',true); }
  } catch (failure) { if (active()) showNotice(failure.message); }
  finally { visibility.value = deck.value.visibility; savingVisibility.value = false; }
}
async function changeDeck(remove) {
  menu.value.open = false;
  if (deckBusy.value || pending.value) return;
  const title = remove ? null : window.prompt('New deck title:',deck.value.title);
  if (remove ? !window.confirm('Delete “' + deck.value.title + '”? This permanently removes its cards and study history.') : title === null) return;
  deckBusy.value = true;
  try {
    if (remove) { await api(path,{method:'DELETE'}); if (active()) await router.push('/flashcards'); }
    else {
      const changed = await api(path,{method:'PATCH',body:{title}});
      if (active()) Object.assign(deck.value,changed);
    }
  } catch (failure) { if (active()) showNotice(failure.message); }
  finally { deckBusy.value = false; }
}
async function deleteCard(card) {
  if (deleting.value || !window.confirm('Delete this flashcard? Existing study sessions keep their saved copy.')) return;
  deleting.value = true;
  try {
    await api('/cards/' + card.id,{method:'DELETE'});
    if (!active()) return;
    if (card.id === editing.value?.id) await router.push('/deck/' + deckId);
    else cards.value = cards.value.filter(item => item.id !== card.id);
  } catch (failure) { if (active()) showNotice(failure.message); }
  finally { deleting.value = false; }
}
</script>
<template>
  <ResourceState v-if="!deck" :error="error" variant="list"/>
  <div v-else class="deck-workspace" @click="menu && !menu.contains($event.target) && (menu.open = false)">
    <div class="breadcrumbs"><a href="/flashcards">Flashcards</a><span>/</span><span>{{ deck.title }}</span></div>
    <div class="page-heading"><div><p class="eyebrow">Your study deck</p><h1>{{ deck.title }}</h1><p class="muted"><span data-card-count>{{ cards.length }}</span> / 150 cards</p></div>
      <div class="actions deck-heading-actions"><button type="submit" form="card-form" id="study-deck" data-intent="study" :disabled="pending || deckBusy">Study deck</button>
        <details class="deck-actions" ref="menu" @keydown.esc="menu.open = false; menu.querySelector('summary').focus()"><summary class="button secondary flat-button" aria-label="Deck actions" title="Deck actions"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M4 6h16M4 12h16M4 18h16"/></svg></summary>
          <div class="deck-actions-list"><button id="rename" class="secondary small flat-button" :disabled="deckBusy" @click="changeDeck(false)">Rename deck</button><button id="delete-deck" class="danger small flat-button" :disabled="deckBusy" @click="changeDeck(true)">Delete deck</button></div>
        </details>
      </div>
    </div>
    <section class="visibility-controls panel" aria-label="Deck sharing">
      <label for="owner-visibility">Visibility</label><select id="owner-visibility" v-model="visibility" :disabled="savingVisibility"><VisibilityOptions/></select>
      <button id="save-visibility" type="button" class="secondary small flat-button" :disabled="savingVisibility" @click="saveVisibility">Save visibility</button>
      <CopyButton id="copy-share-link" :disabled="deck.visibility === 'private' || !share" :value="share">Copy share link</CopyButton><span id="visibility-message" role="status"></span>
    </section>
    <form id="card-form" ref="form" class="card-composer panel" novalidate @keydown="shortcut" @submit.prevent="submit"><fieldset class="editor-fields" :disabled="pending || deckBusy">
      <legend class="sr-only">{{ editing ? 'Edit flashcard' : 'Create a flashcard' }}</legend><div class="composer-heading"><h2 id="editor-card-number">Card no. {{ editing ? numberOf(editing) : Math.min(cards.length + 1,150) }}</h2><span class="badge">Question + answer</span></div>
      <div class="editor-sides"><EditorSide v-model="draft.front" side="front" label="Question" placeholder="What do you want to remember?" :photo="images.front" :disabled="full" @photo="choosePhoto('front',$event)" @remove="removePhoto('front')"/>
        <EditorSide v-model="draft.back" side="back" label="Answer" placeholder="Write the answer here…" :photo="images.back" :disabled="full" @photo="choosePhoto('back',$event)" @remove="removePhoto('back')"/></div>
      <p class="hint">250 characters per side · One photo per card</p><p class="hint"><kbd>Ctrl / ⌘ + Enter</kbd> {{ editing ? 'Save changes' : 'Save and continue' }}</p>
      <div class="composer-actions"><span id="card-count" class="muted" role="status" aria-live="polite"><span data-card-count>{{ cards.length }}</span> cards saved<span v-for="id in increments" :key="id" class="saved-increment" aria-hidden="true">+1</span></span>
        <div class="actions"><a v-if="editing" :href="'/deck/' + deckId" class="button secondary">Cancel edit</a><button ref="saveButton" type="submit" id="next-card" data-intent="save" :disabled="full || pending || deckBusy">{{ editing ? 'Save changes' : 'Next Card →' }}</button></div>
      </div>
    </fieldset></form>
    <div class="section-heading"><h2>Cards <span class="muted">(<span data-card-count>{{ cards.length }}</span>)</span></h2><label class="sr-only" for="card-order">Card order</label><select id="card-order" class="card-order" v-model="order" @change="page = 1"><option value="desc">Most recent first</option><option value="asc">Least recent first</option></select></div>
    <label class="sr-only" for="saved-card-search">Find a saved card</label><input id="saved-card-search" v-model="query" type="search" placeholder="Find a saved question or answer…" autocomplete="off" @input="page = 1">
    <div id="saved-cards" ref="savedList" class="card-list">
      <article v-for="card in saved" :key="card.id" class="saved-card" :class="{'is-editing':card.id === editing?.id}">
        <div class="saved-card-heading"><span class="badge">Card {{ numberOf(card) }}</span><div class="actions">
          <a class="button secondary small card-icon-action flat-button" :aria-label="'Edit card ' + numberOf(card)" title="Edit card" :href="'/deck/' + deckId + '/edit/' + card.id"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d="m15 4 5 5M4 20l5-1L20 8a3.5 3.5 0 0 0-5-5L4 14z"/></svg></a>
          <button type="button" class="danger small card-icon-action flat-button" :data-delete="card.id" :aria-label="'Delete card ' + numberOf(card)" title="Delete card" :disabled="deleting" @click="deleteCard(card)"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d="M4 6h16M9 6V3h6v3M6 6l1 15h10l1-15M10 10v7m4-7v7"/></svg></button>
        </div></div>
        <div class="saved-card-sides"><div class="saved-side"><span class="content-label">Question</span><CardContent :text="card.front" :image="card.front_image" alt="Question photo" preview/></div>
          <div class="saved-side answer"><span class="content-label">Answer</span><CardContent :text="card.back" :image="card.back_image" alt="Answer photo" preview/></div></div>
      </article>
      <div v-if="!cards.length" class="empty"><h2>Your first card starts above.</h2><p class="muted">Write a question and its answer, then choose Next Card.</p></div>
    </div>
    <p v-if="cards.length && !matches.length" id="saved-card-empty" class="muted">No matching cards.</p>
    <nav ref="pages" id="saved-card-pages" class="saved-card-pages" aria-label="Saved card pages" :hidden="pageCount === 1">
      <button type="button" class="secondary small flat-button" :disabled="page === 1" @click="step(-1,$event)">Previous</button><span aria-live="polite">Page {{ page }} of {{ pageCount }}</span><button type="button" class="secondary small flat-button" :disabled="page === pageCount" @click="step(1,$event)">Next</button>
    </nav>
    <PreviousSession :deck-id="deckId"/>
  </div>
</template>
