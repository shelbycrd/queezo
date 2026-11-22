<script setup>
import {computed, nextTick, onScopeDispose, ref, watch} from 'vue';
import {useRoute} from 'vue-router';
import {api} from '../../js/api.js';
import {playAnswerSound, preparePageSound} from '../../js/audio.js';
import {sharedAnswers, sharedChoices, shuffle} from '../../js/shared-practice.js';
import {validateTiming} from '../../js/study-options.js';
import {useEvent, useResource} from '../composables/lifecycle.js';
import {closeIcon} from '../services/format.js';
import CardContent from '../components/CardContent.vue';

const {token} = defineProps({token:String});
const {query} = useRoute();
const {data:deck,error} = useResource(signal => api('/shared/decks/' + encodeURIComponent(token),{signal}));
const deckLink = {name:'shared',params:{token}};
const cards = computed(() => deck.value ? shuffle(deck.value.cards) : []);
const answers = computed(() => sharedAnswers(cards.value));
const multiple = computed(() => query.type === 'multiple-choice' && answers.value.length >= 4);
const index = ref(0), revealed = ref(false), eliminated = ref(null), selected = ref(null);
const correct = ref(0), timeouts = ref(0), done = ref(false), expired = ref(false);
const question = ref(), nextButton = ref();
const now = ref(Date.now()), deadline = ref(0);
const card = computed(() => cards.value[index.value]);
const choices = computed(() => multiple.value && card.value ? sharedChoices(card.value.back,answers.value) : []);
const remaining = computed(() => Math.max(0, Math.ceil((deadline.value - now.value) / 1000)));
const clock = computed(() => [Math.floor(remaining.value / 60),remaining.value % 60]
  .map(value => String(value).padStart(2,'0')).join(':'));
let timing = {mode:'unlimited'};
try {
  timing = validateTiming(query.timing ?? 'unlimited',query.scope,query.amount);
} catch { /* Invalid timing parameters use unlimited practice. */ }

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
  eliminated.value = null;
  selected.value = null;
  if (timing.scope === 'question') resetClock();
  void nextTick(() => question.value?.focus());
}
function choose(choice) {
  if (done.value || revealed.value || choice === eliminated.value) return;
  preparePageSound();
  const isCorrect = choice === card.value.back;
  playAnswerSound(isCorrect);
  if (!isCorrect && eliminated.value === null) {
    eliminated.value = choice;
    return;
  }
  selected.value = choice;
  if (isCorrect) correct.value++;
  reveal();
}
function tick() {
  if (!deadline.value || done.value) return;
  now.value = Date.now();
  if (remaining.value) return;
  if (timing.scope === 'deck') {
    expired.value = true;
    done.value = true;
  } else if (!revealed.value) {
    if (multiple.value) { timeouts.value++; advance(); }
    else reveal();
  }
}
if (timing.mode === 'timed') {
  watch(card, current => { if (current && !deadline.value) resetClock(); }, {flush:'sync'});
  const timer = setInterval(tick,250);
  onScopeDispose(() => clearInterval(timer));
}
useEvent(document,'keydown', event => {
  if (event.key !== 'Enter' || event.defaultPrevented || multiple.value || !card.value || done.value ||
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
    <p v-else-if="!deck" class="muted" role="status">Loading deck…</p>
    <p v-else-if="!cards.length" class="muted">This deck has no cards to study yet.</p>
    <section v-else-if="done" class="panel mc-panel" aria-labelledby="shared-summary">
      <h2 id="shared-summary">{{ expired ? 'Time is up' : 'Practice complete' }}</h2>
      <p v-if="multiple">{{ correct }} of {{ index }} correct<span v-if="timeouts"> · {{ timeouts }} timed out</span></p>
      <p v-else>{{ index }} of {{ cards.length }} cards reviewed</p>
      <RouterLink class="button secondary" :to="deckLink">Return to deck</RouterLink>
    </section>

    <template v-else>
      <div v-if="timing.mode === 'timed'" class="study-clock"><span>{{ timing.scope === 'question' ? 'Question time' : 'Deck time' }} left</span><strong role="timer">{{ clock }}</strong></div>
      <div class="progress-text"><strong>{{ multiple ? 'Question' : 'Card' }} {{ index + 1 }} of {{ cards.length }}</strong></div>
      <progress :max="cards.length" :value="index" aria-label="Cards completed"></progress>
      <article class="study-sheet" :class="{'answer-revealed':revealed && !multiple}">
        <section class="study-question">
          <h2 class="content-label" ref="question" tabindex="-1">Question</h2>
          <CardContent :text="card.front" :image="card.front_image" alt="Question photo"/>
        </section>
        <section v-if="revealed && !multiple" class="study-answer" aria-label="Revealed answer">
          <span class="content-label">Answer</span>
          <CardContent :text="card.back" :image="card.back_image" alt="Answer photo"/>
        </section>
        <div v-else-if="!multiple" class="study-reveal-prompt">
          <button type="button" class="secondary" @click="reveal">Reveal answer <kbd>Enter</kbd></button>
        </div>
      </article>

      <fieldset v-if="multiple" class="mc-choices">
        <legend>Answer choices</legend>
        <div class="mc-options">
          <button v-for="(choice,position) in choices" :key="choice" type="button"
            class="mc-option flat-button" :disabled="revealed || eliminated === choice"
            :class="{'mc-correct':revealed && choice === card.back,'mc-incorrect':eliminated === choice || (selected === choice && choice !== card.back)}"
            @click="choose(choice)">
            <span class="mc-letter" aria-hidden="true">{{ String.fromCharCode(65 + position) }}</span>
            <span class="mc-option-text">{{ choice }}</span>
            <small class="mc-option-mark">
              <span :class="{'is-visible':revealed && choice === card.back}">Correct answer</span>
              <span :class="{'is-visible':eliminated === choice || selected === choice}">{{ eliminated === choice ? 'First guess' : 'Your choice' }}</span>
            </small>
          </button>
        </div>
      </fieldset>
      <img v-if="multiple && revealed && card.back_image" class="card-photo" :src="card.back_image" alt="Correct answer photo">
      <div class="actions mc-actions">
        <button v-if="revealed" type="button" ref="nextButton" @click="advance">{{ index + 1 === cards.length ? 'See results' : multiple ? 'Next question' : 'Next card' }}</button>
        <p v-else-if="multiple" class="muted" role="status">{{ eliminated === null ? 'Two attempts' : 'Try again. One attempt left.' }}</p>
      </div>
    </template>
  </div>
</template>
