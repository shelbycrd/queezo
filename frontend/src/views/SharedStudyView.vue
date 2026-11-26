<script setup>
import {computed, nextTick, onScopeDispose, ref, watch} from 'vue';
import {useRoute, useRouter} from 'vue-router';
import {api} from '../../js/api.js';
import {shuffle} from '../../js/shared-practice.js';
import {validateTiming} from '../../js/study-options.js';
import {useEvent, useResource} from '../composables/lifecycle.js';
import {closeIcon} from '../services/format.js';
import {sharedMultipleChoiceRoute} from '../services/study-dialog.js';
import CardContent from '../components/CardContent.vue';
import LoadingSkeleton from '../components/LoadingSkeleton.vue';

const {token} = defineProps({token:String});
const {query} = useRoute(), router = useRouter();
const multiple = query.type === 'multiple-choice';
const deckLink = {name:'shared',params:{token}};
let timing = {mode:'unlimited'};
try {
  timing = validateTiming(query.timing ?? 'unlimited',query.scope,query.amount);
} catch { /* Invalid timing parameters use unlimited practice. */ }

const {data:deck,error} = useResource(async signal => {
  const path = '/shared/decks/' + encodeURIComponent(token);
  if (!multiple) return api(path,{signal});
  const body = timing.mode === 'timed' ? {scope:timing.scope,seconds:timing.seconds} : undefined;
  const session = await api(path + '/multiple-choice',{method:'POST',body,signal});
  if (!signal.aborted) await router.replace(sharedMultipleChoiceRoute(session.id,token));
  return null;
});
const cards = computed(() => deck.value ? shuffle(deck.value.cards) : []);
const index = ref(0), revealed = ref(false), done = ref(false), expired = ref(false);
const question = ref(), nextButton = ref();
const now = ref(Date.now()), deadline = ref(0);
const card = computed(() => cards.value[index.value]);
const remaining = computed(() => Math.max(0, Math.ceil((deadline.value - now.value) / 1000)));
const clock = computed(() => [Math.floor(remaining.value / 60),remaining.value % 60]
  .map(value => String(value).padStart(2,'0')).join(':'));

function resetClock() {
  now.value = Date.now();
  deadline.value = now.value + timing.seconds * 1000;
}
function reveal() {
  if (revealed.value) return;
  revealed.value = true;
  void nextTick(() => nextButton.value?.focus());
}
function advance() {
  index.value++;
  if (index.value >= cards.value.length) {
    done.value = true;
    return;
  }
  revealed.value = false;
  if (timing.scope === 'question') resetClock();
  void nextTick(() => question.value?.focus());
}
function tick() {
  if (!deadline.value || done.value) return;
  now.value = Date.now();
  if (remaining.value) return;
  if (timing.scope === 'deck') {
    expired.value = true;
    done.value = true;
  } else if (!revealed.value) reveal();
}
if (timing.mode === 'timed') {
  watch(card, current => { if (current && !deadline.value) resetClock(); }, {flush:'sync'});
  const timer = setInterval(tick,250);
  onScopeDispose(() => clearInterval(timer));
}
useEvent(document,'keydown', event => {
  if (event.key !== 'Enter' || event.defaultPrevented || !card.value || done.value ||
      event.target.closest?.('button,a,input,textarea,select,[contenteditable],dialog')) return;
  event.preventDefault();
  if (revealed.value) advance();
  else reveal();
});
</script>

<template>
  <div class="study-shell mc-shell">
    <div class="study-heading">
      <RouterLink class="button secondary flat-button study-exit" :to="deckLink" aria-label="Return to shared deck" v-html="closeIcon"/>
      <div><p class="eyebrow">{{ multiple ? 'Multiple-Choice Mode' : 'Classic Mode' }}</p><h1>{{ deck?.title || 'Study shared deck' }}</h1></div>
    </div>

    <p v-if="error" class="muted" role="alert">{{ error }}</p>
    <LoadingSkeleton v-else-if="!deck" variant="card" :label="multiple ? 'Preparing your session…' : 'Loading deck…'"/>
    <p v-else-if="!cards.length" class="muted">This deck has no cards to study yet.</p>
    <section v-else-if="done" class="panel mc-panel" aria-labelledby="shared-summary">
      <h2 id="shared-summary">{{ expired ? 'Time is up' : 'Practice complete' }}</h2>
      <p>{{ index }} of {{ cards.length }} cards reviewed</p>
      <RouterLink class="button secondary" :to="deckLink">Return to deck</RouterLink>
    </section>

    <template v-else>
      <div v-if="timing.mode === 'timed'" class="study-clock"><span>{{ timing.scope === 'question' ? 'Question time' : 'Deck time' }} left</span><strong role="timer">{{ clock }}</strong></div>
      <div class="progress-text"><strong>Card {{ index + 1 }} of {{ cards.length }}</strong></div>
      <progress :max="cards.length" :value="index" aria-label="Cards completed"></progress>
      <article class="study-sheet" :class="{'answer-revealed':revealed}">
        <section class="study-question">
          <h2 class="content-label" ref="question" tabindex="-1">Question</h2>
          <CardContent :text="card.front" :image="card.front_image" alt="Question photo"/>
        </section>
        <section v-if="revealed" class="study-answer" aria-label="Revealed answer">
          <span class="content-label">Answer</span>
          <CardContent :text="card.back" :image="card.back_image" alt="Answer photo"/>
        </section>
        <div v-else class="study-reveal-prompt">
          <button type="button" class="secondary" @click="reveal">Reveal answer <kbd>Enter</kbd></button>
        </div>
      </article>

      <div class="actions mc-actions">
        <button v-if="revealed" type="button" ref="nextButton" @click="advance">{{ index + 1 === cards.length ? 'See results' : 'Next card' }}</button>
      </div>
    </template>
  </div>
</template>
