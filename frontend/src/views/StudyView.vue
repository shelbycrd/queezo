<script setup>
import {computed, nextTick, onScopeDispose, reactive, ref, watch} from 'vue';
import {useRouter} from 'vue-router';
import {api} from '../../js/api.js';
import {studyShortcut} from '../../js/card-content.js';
import {loadTiming,saveTiming} from '../../js/study-options.js';
import {closeIcon,plural} from '../services/format.js';
import {showNotice} from '../services/notice.js';
import {useEvent,useResource} from '../composables/lifecycle.js';
import CardContent from '../components/CardContent.vue';
import ResourceState from '../components/ResourceState.vue';

const {sessionId} = defineProps({sessionId:String});
const router = useRouter();
const path = '/study/' + sessionId;
const {data:state,error,active,signal} = useResource(signal => api(path,{signal}));
const timing = reactive(loadTiming(sessionId));
const pending = ref(false), ending = ref(false), timedOut = ref(false), question = ref();
const now = ref(Date.now());
const card = computed(() => state.value?.current_card);
const remaining = computed(() => Math.max(0,Math.ceil(((timing.deadline || 0) - now.value)/1000)));
const timeText = computed(() => String(Math.floor(remaining.value / 60)).padStart(2,'0') + ':' + String(remaining.value % 60).padStart(2,'0'));
const body = () => ({presentation_number:state.value.presentation_number,presentation_token:state.value.presentation_token});
const summary = () => router.push('/summary/' + sessionId);
watch(state, current => {
  if (!current) return;
  if (current.status !== 'active') { void summary(); return; }
  if (timing.mode === 'timed' && (!timing.deadline || (timing.scope === 'question' && timing.presentation !== current.presentation_number))) {
    timing.deadline = Date.now() + timing.seconds * 1000;
    timing.presentation = current.presentation_number;
    delete timing.expiredPresentation;
    saveTiming(sessionId,timing);
    timedOut.value = false;
  }
  tick();
}, {flush:'sync'});

async function recover(failure) {
  if (!active()) return;
  showNotice(failure.message);
  try { state.value = await api(path,{signal}); } catch { /* Preserve the original actionable error. */ }
}
async function action(difficulty) {
  if (!state.value || pending.value || ending.value || (!difficulty && state.value.revealed)) return;
  pending.value = true;
  try {
    if (!state.value.revealed) {
      const revealed = await api(path + '/reveal',{method:'POST',body:body()});
      if (!active()) return;
      state.value = revealed;
    }
    if (difficulty) {
      const rated = await api(path + '/rate',{method:'POST',body:{...body(),difficulty}});
      if (!active()) return;
      state.value = rated;
      showNotice('');
    }
    await nextTick();
    question.value?.focus({preventScroll:true});
  } catch (failure) { await recover(failure); }
  finally { pending.value = false; }
}
async function leave(timeout = false) {
  if (!state.value || pending.value) return;
  pending.value = true;
  if (timeout) ending.value = true;
  try {
    await api(path + '/exit',{method:'POST'});
    if (active()) await router.push(timeout ? '/summary/' + sessionId : '/deck/' + state.value.deck_id);
  } catch (failure) {
    if (active()) showNotice(failure.message + (timeout ? ' Use Back to deck to end the session.' : ''));
  } finally { pending.value = false; }
}
function tick() {
  if (timing.mode !== 'timed' || state.value?.status !== 'active') return;
  now.value = Date.now();
  if (remaining.value || pending.value || ending.value) return;
  if (timing.scope === 'deck') { void leave(true); return; }
  timedOut.value = true;
  if (timing.expiredPresentation !== state.value.presentation_number) {
    timing.expiredPresentation = state.value.presentation_number;
    saveTiming(sessionId,timing);
    void action();
  }
}
if (timing.mode === 'timed') {
  const timer = setInterval(tick,250);
  onScopeDispose(() => clearInterval(timer));
}
useEvent(document,'keydown', event => {
  const target = event.target;
  if (!state.value || !target.closest || target.closest('input,textarea,select,[contenteditable],dialog,#account-controls,#main-navigation,.sidebar-settings')) return;
  const command = studyShortcut(event);
  if (!command || (command === 'reveal' && target.closest('.study-exit'))) return;
  event.preventDefault();
  void action(command === 'reveal' ? undefined : command);
});
const ratings = [['hard','Hard','More practice'],['normal','Normal','Getting there'],['easy','Easy','Feeling confident']];
</script>
<template>
  <div v-if="!card" class="study-shell">
    <div class="study-heading"><RouterLink class="button secondary flat-button study-exit" to="/flashcards" aria-label="Return to Flashcards" v-html="closeIcon"/></div>
    <ResourceState :error="error" variant="study-card"/>
  </div>
  <div v-else class="study-shell" :aria-busy="pending">
    <div class="study-heading"><button type="button" class="secondary flat-button study-exit" aria-label="Return to deck" :disabled="pending" @click="leave()" v-html="closeIcon"></button><div><p class="eyebrow">A little focused recall</p><h1>{{ state.deck_title }}</h1></div></div>
    <div v-if="timing.mode === 'timed'" class="study-clock"><span>{{ timing.scope === 'question' ? 'Time for this question' : 'Time for this deck' }}</span><strong id="study-time-left" role="timer">{{ timeText }}</strong><span id="study-time-message">{{ timedOut ? 'Time is up. Review the answer and rate your recall.' : '' }}</span></div>
    <div class="progress-text"><span>{{ state.completed_cards }} of {{ state.total_cards }} cards complete</span><span>{{ plural(state.total_reviews,'review') }}</span></div><progress :max="state.total_cards" :value="state.completed_cards" aria-label="Completed flashcards"></progress>
    <article class="study-sheet" :class="{'answer-revealed':state.revealed}" aria-label="Flashcard"><section class="study-question" ref="question" tabindex="-1"><span class="content-label">Question</span><CardContent :text="card.front" :image="card.front_image" alt="Question photo"/></section>
      <section v-if="state.revealed" class="study-answer" id="answer" aria-label="Revealed answer"><span class="content-label">Answer</span><CardContent :text="card.back" :image="card.back_image" alt="Answer photo"/></section>
      <div v-else class="study-reveal-prompt"><button id="reveal" type="button" class="secondary" :disabled="pending || ending" @click="action()">Reveal answer <kbd>Enter</kbd></button><p>Press Enter to reveal</p></div>
    </article>
    <div class="study-actions"><p class="muted">{{ state.revealed ? 'How well did you remember?' : 'Know it already? Rate your recall to reveal and continue.' }}</p>
      <div class="ratings recall-ratings"><button v-for="([key,label,hint],index) in ratings" :key="key" :class="key" :data-rating="key" :disabled="pending || ending" @click="action(key)"><kbd>{{ index + 1 }}</kbd><span>{{ label }}</span><small>{{ hint }}</small></button></div>
    </div>
    <p class="shortcut-hint">{{ plural(card.review_count,'review') }} of this card{{ card.review_count ? ' · Current target: ' + card.target_reviews : '' }}</p>
  </div>
</template>
