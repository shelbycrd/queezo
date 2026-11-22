<script setup>
import {computed, nextTick, onMounted, onScopeDispose, ref, shallowRef, watch} from 'vue';
import {multipleChoiceSession, scoreSummary} from '../../js/multiple-choice-session.js';
import {safeImageUrl} from '../../js/card-content.js';
import {authVersion} from '../../js/auth-state.js';
import {chooseStudy} from '../services/study-dialog.js';
import {playAnswerSound, preparePageSound} from '../../js/audio.js';
import {closeIcon,plural} from '../services/format.js';
import {useLifetime} from '../composables/lifecycle.js';
import CardContent from '../components/CardContent.vue';

const FAILURE_LABELS = {
  generation_failed:'Could not find three distinct choices. Check Ollama or add cards with different answers.',
  insufficient_distractors:'Too few distinct answers for this card. Add cards with different answers or retry with Ollama.',
  ollama_unavailable:'Ollama is unavailable. Check that it is running and the model is installed, then retry.',
  generation_timeout:'Ollama took too long to respond. Retry the failed cards.',
  invalid_ai_response:'Ollama returned an unreadable response. Retry or add cards with different answers.',
  card_missing:'The card was deleted or is no longer accessible.',
  card_changed:'The card changed during preparation.',
  preparation_timeout:'Preparation ran out of time.',
  study_timeout:'The study timer ended before this question was prepared.',
  interrupted:'Preparation was interrupted.',
  history_media_limit:'The account reached its study photo storage limit.',
  preparation_failed:'Could not prepare this card.',
};

const {sessionId} = defineProps({sessionId:String});
const {active} = useLifetime(), accountVersion = authVersion();
const view = shallowRef({}), choosing = ref(false);
const focus = ref(), feedback = ref(), clockNow = ref(Date.now());
const session = computed(() => view.value.session);
const question = computed(() => view.value.question);
const grade = computed(() => view.value.grade);
const pending = computed(() => view.value.pending);
const problem = computed(() => view.value.problem);
const deckPath = computed(() => session.value ? '/deck/' + session.value.deck_id : '/decks');
const deckLink = computed(() => '#' + deckPath.value);
const phase = computed(() => {
  if (problem.value) return 'problem';
  if (grade.value) return 'feedback:' + question.value.id;
  if (session.value?.status === 'active' && question.value) return (question.value.eliminated_option_id ? 'retry:' : 'question:') + question.value.id;
  if (session.value?.status === 'active' && session.value.study_started !== false) return 'waiting';
  return session.value?.status || 'loading';
});
const preparation = computed(() => phase.value === 'preparing' || phase.value === 'failed' || session.value?.can_start);
const finished = computed(() => phase.value === 'completed');
const failed = computed(() => phase.value === 'failed');
const unavailable = computed(() => problem.value && [401,404].includes(problem.value.status));
const ready = computed(() => session.value.preparing ? session.value.progress.total - session.value.progress.failed : session.value.progress.ready);
const completed = computed(() => session.value.answered + (session.value.timed_out ?? 0));
const ordinal = computed(() => completed.value + (grade.value ? 0 : 1));
const image = computed(() => safeImageUrl(grade.value?.back_image));
const isCorrect = option => option.id === grade.value?.correct_option?.id;
const isChosen = option => option.id === grade.value?.selected_option_id;
const isEliminated = option => option.id === question.value?.eliminated_option_id;
const showClock = computed(() => view.value.clock && !problem.value && (grade.value || session.value?.status === 'active'));
const clockLabel = computed(() => session.value?.timing?.scope === 'deck' ? 'Deck time' : 'Question time');
const clock = computed(() => {
  const seconds = Math.max(0,Math.ceil((view.value.clock - clockNow.value)/1000));
  return Math.floor(seconds/60) + ':' + String(seconds%60).padStart(2,'0');
});
const stats = computed(() => {
  const score = scoreSummary(session.value);
  const rows = [['Correct',score.correct],['Incorrect',score.incorrect],['Questions',score.total],['Accuracy',score.accuracy === null ? '—' : score.accuracy + '%']];
  if (session.value.timed_out) rows.splice(2,0,['Timed out',session.value.timed_out]);
  return rows;
});
const controller = multipleChoiceSession(sessionId, {
  update:state => { clockNow.value = Date.now(); view.value = state; },
  active:() => active() && authVersion() === accountVersion,
  answerFeedback:playAnswerSound,
});
watch(phase, async current => {
  await nextTick();
  const showingFeedback = current.startsWith('feedback:') || current.startsWith('retry:');
  (showingFeedback ? feedback.value : focus.value)?.focus({preventScroll:showingFeedback});
});
onMounted(() => void controller.refresh());
const timer = setInterval(() => {
  if (showClock.value && (!grade.value || (session.value.status === 'active' && session.value.timing.scope === 'deck'))) clockNow.value = Date.now();
},250);
onScopeDispose(() => { controller.stop(); clearInterval(timer); });
function selectAnswer(option) {
  preparePageSound();
  void controller.answer(option.id);
}
async function again() {
  choosing.value = true;
  try { await chooseStudy(session.value.deck_id,{mode:'multiple-choice'}); } finally { choosing.value = false; }
}
</script>
<template>
  <div class="study-shell mc-shell">
    <div class="study-heading"><RouterLink class="button secondary flat-button study-exit" :to="deckPath" :aria-label="session ? 'Return to deck' : 'Return to Flashcards'" v-html="closeIcon"/>
      <div><p class="eyebrow">Multiple-Choice Mode</p><h1>{{ session?.deck_title || 'Multiple-Choice Study' }}</h1></div>
    </div>
    <p v-if="view.message" role="status" class="mc-note">{{ view.message }}</p>
    <div v-if="showClock" class="study-clock" role="timer" :aria-label="clockLabel + ' remaining'"><span>{{ clockLabel }} left</span><strong data-mc-clock>{{ clock }}</strong></div>
    <div class="mc-content" :aria-busy="Boolean(pending)">
      <section v-if="problem" class="panel mc-panel"><h2 ref="focus" tabindex="-1">{{ unavailable ? 'Session unavailable' : 'Couldn’t load study progress' }}</h2>
        <p role="alert" class="muted">{{ problem.message }}</p>
        <p v-if="!unavailable" class="muted">Reconnect to load the latest saved progress before continuing.</p>
        <div class="actions mc-actions"><button v-if="!unavailable" type="button" @click="controller.refresh()">Try again</button><a class="button secondary flat-button" :href="deckLink">{{ session ? 'Return to deck' : 'Return to Flashcards' }}</a></div>
      </section>
      <template v-else-if="grade || (session?.status === 'active' && question)">
        <div class="progress-text"><strong>Question {{ ordinal }} of {{ ready }}</strong><span>{{ session.answered }} answered{{ session.timed_out ? ' · ' + session.timed_out + ' timed out' : '' }}</span></div>
        <progress :max="ready" :value="completed" aria-label="Questions completed"></progress>
        <article class="study-sheet mc-question"><section class="study-question"><h2 class="content-label" ref="focus" tabindex="-1">Question {{ ordinal }}</h2><CardContent :text="question.front" :image="question.front_image" alt="Question photo"/></section></article>
        <fieldset class="mc-choices" :disabled="Boolean(grade || pending)">
          <legend>Answer choices</legend>
          <div class="mc-options" ref="feedback" tabindex="-1" role="group"
            :aria-label="grade ? (grade.is_correct ? 'Correct' : 'Incorrect') + '. Answer choices.' : 'Answer choices'"
            :aria-describedby="grade ? undefined : 'mc-attempts'">
            <button v-for="(option,index) in question.options" :key="option.id" type="button"
              class="mc-option flat-button" :disabled="isEliminated(option)"
              :class="{'mc-correct':isCorrect(option),'mc-incorrect':isEliminated(option) || (isChosen(option) && !isCorrect(option))}"
              @click="selectAnswer(option)">
              <span class="mc-letter" aria-hidden="true">{{ String.fromCharCode(65 + index) }}</span>
              <span class="mc-option-text">{{ option.text }}</span>
              <small class="mc-option-mark">
                <span :class="{'is-visible':isCorrect(option)}">Correct answer</span>
                <span :class="{'is-visible':isChosen(option) || isEliminated(option)}">{{ isEliminated(option) ? 'First guess' : 'Your choice' }}</span>
              </small>
            </button>
          </div>
        </fieldset>
        <div class="actions mc-actions">
          <button v-if="grade" type="button" :disabled="Boolean(pending)" @click="controller.next()">{{ pending === 'next' ? 'Loading…' : session.status === 'completed' ? 'See results' : 'Next question' }}</button>
          <p v-else id="mc-attempts" class="muted" role="status">{{ question.eliminated_option_id ? 'Try again. One attempt left.' : question.attempts_remaining === 2 ? 'Two attempts' : 'One attempt' }}</p>
        </div>
        <img v-if="image" class="card-photo" :src="image" alt="Correct answer photo">
      </template>
      <section v-else-if="phase === 'waiting'" class="panel mc-panel"><h2 ref="focus" tabindex="-1">{{ session.deck_time_over ? 'Finishing your session' : 'Preparing the next question' }}</h2>
        <p class="muted">{{ session.deck_time_over ? 'The deck timer has ended.' : 'Your place is saved. The next question will open when it’s ready.' }}</p>
      </section>
      <template v-else-if="finished">
        <div class="summary-heading"><div class="check" aria-hidden="true">✓</div><h2 ref="focus" tabindex="-1">Session complete</h2>
          <p v-if="session.progress.failed" class="muted">{{ plural(session.progress.failed,'card') }} skipped during preparation.</p></div>
        <div class="summary-grid mc-summary-grid"><div v-for="[label,value] in stats" :key="label" class="stat"><p class="muted">{{ label }}</p><div class="value">{{ value }}</div></div></div>
        <div class="actions mc-actions"><button type="button" :disabled="choosing" @click="again">Study again</button><a class="button secondary flat-button" :href="deckLink">Return to deck</a></div>
      </template>
      <section v-else-if="['expired','cancelled'].includes(phase)" class="panel mc-panel">
        <h2 ref="focus" tabindex="-1">{{ phase === 'expired' ? 'Session expired' : 'Session cancelled' }}</h2>
        <p class="muted">{{ phase === 'expired' ? 'Multiple-Choice sessions expire after 24 hours.' : 'This session has ended.' }} You can start a new session from your deck.</p>
        <div class="actions mc-actions"><a class="button secondary flat-button" :href="deckLink">Return to deck</a></div>
      </section>
      <section v-else-if="preparation" class="panel mc-panel" aria-labelledby="mc-state-heading">
        <h2 id="mc-state-heading" ref="focus" tabindex="-1">{{ failed ? (session.progress.ready ? 'Some questions couldn’t be prepared' : 'Questions couldn’t be prepared') : 'Preparing your questions' }}</h2>
        <p class="muted">{{ failed ? (session.progress.ready ? 'Retry failed cards, study the ready questions, or return to your deck.' : 'Retry the failed cards or return to your deck to use Classic Mode.') : 'Checking the first questions in your shuffled deck.' }}</p>
        <p v-if="failed" class="muted">{{ session.progress.ready }} ready · {{ session.progress.failed }} failed</p>
        <div v-else class="mc-preparation-progress" role="status"><div class="progress-text"><strong>{{ session.opening.ready }} of {{ session.opening.target }} opening questions ready</strong></div><progress :max="session.opening.target" :value="session.opening.ready" aria-label="Opening questions ready"></progress></div>
        <details v-if="session.failures.length" class="mc-failures"><summary>See failed cards ({{ session.failures.length }})</summary><ul><li v-for="failure in session.failures" :key="failure.card_id"><strong>Card ID {{ failure.card_id }}</strong><span>{{ FAILURE_LABELS[failure.reason] || 'Could not prepare this card.' }}</span></li></ul></details>
        <div class="actions mc-actions"><button v-if="failed" type="button" :disabled="Boolean(pending)" @click="controller.transition('retry')">{{ pending === 'retry' ? 'Retrying…' : 'Retry failed cards' }}</button>
          <button v-if="failed && session.progress.ready" type="button" class="secondary flat-button" :disabled="Boolean(pending)" @click="controller.transition('continue')">{{ pending === 'continue' ? 'Opening…' : 'Study ' + plural(session.progress.ready,'ready question') }}</button>
          <button type="button" class="secondary flat-button" :disabled="Boolean(pending)" @click="controller.transition('cancel')">{{ pending === 'cancel' ? 'Cancelling…' : 'Cancel preparation' }}</button>
        </div>
      </section>
      <p v-else class="muted" role="status">Loading study session…</p>
    </div>
  </div>
</template>
