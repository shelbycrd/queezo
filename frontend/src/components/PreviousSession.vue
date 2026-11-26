<script setup>
import {ref, shallowRef} from 'vue';
import {api} from '../../js/api.js';
import {SESSION_LABELS} from '../../js/multiple-choice-session.js';
import {date, duration, plural} from '../services/format.js';
import {useLifetime} from '../composables/lifecycle.js';
import LoadingSkeleton from './LoadingSkeleton.vue';

const {deckId} = defineProps({deckId:String});
const {signal, active} = useLifetime();
const sessions = shallowRef(null), busy = ref(false), error = ref(false);
const classicLabels = {active:'In progress', completed:'Completed', exited:'Exited'};

async function load() {
  if (busy.value) return;
  busy.value = true;
  error.value = false;
  const path = '/decks/' + deckId;
  try {
    const [[classic], [multiple]] = await Promise.all([
      api(path + '/sessions?limit=1', {signal}),
      api(path + '/multiple-choice/sessions?limit=1', {signal}),
    ]);
    if (!active()) return;
    sessions.value = [
      classic && {
        mode:'Classic', started:classic.started_at, status:classicLabels[classic.status],
        detail:plural(classic.total_reviews, 'review') + ' · ' + plural(classic.total_unique_cards, 'card') +
          ' studied · ' + duration(classic.duration_seconds),
        href:'/' + (classic.status === 'active' ? 'study' : 'summary') + '/' + encodeURIComponent(classic.session_id),
        action:classic.status === 'active' ? 'Resume' : 'Summary',
      },
      multiple && {
        mode:'Multiple-Choice', started:multiple.created_at, status:SESSION_LABELS[multiple.status],
        detail:multiple.answered + ' of ' + multiple.progress.ready + ' answered · ' + multiple.correct + ' correct',
        href:'/multiple-choice/' + encodeURIComponent(multiple.id),
        action:multiple.status === 'completed' ? 'Summary' :
          ['active','preparing','failed'].includes(multiple.status) ? 'Open session' : 'Details',
      },
    ].filter(Boolean).sort((a,b) => Date.parse(b.started) - Date.parse(a.started));
  } catch {
    if (active()) error.value = true;
  } finally {
    busy.value = false;
  }
}
</script>

<template>
  <details class="session-history" @toggle="$event.target.open && load()">
    <summary>Previous Session <span v-if="sessions" class="muted">({{ sessions.length }})</span></summary>
    <LoadingSkeleton v-if="busy" variant="lines" label="Loading previous sessions…"/>
    <template v-else-if="error">
      <p role="status" class="muted">Could not load previous sessions.</p>
      <button type="button" class="secondary small flat-button" @click="load">Try again</button>
    </template>
    <template v-else-if="sessions">
      <div v-if="sessions.length" class="panel">
        <ul class="history-list">
          <li v-for="session in sessions" :key="session.mode">
            <div>
              <p><strong>{{ session.mode }}</strong> · {{ date(session.started) }} · {{ session.status }}</p>
              <p class="muted">{{ session.detail }}</p>
            </div>
            <a class="button secondary small flat-button" :href="session.href"
              :aria-label="session.action + ' · ' + session.mode">{{ session.action }}</a>
          </li>
        </ul>
      </div>
      <p v-else class="muted">Your latest Classic and Multiple-Choice sessions will appear here.</p>
    </template>
  </details>
</template>
