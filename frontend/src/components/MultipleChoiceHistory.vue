<script setup>
import {ref,shallowRef} from 'vue';
import {api} from '../../js/api.js';
import {SESSION_LABELS} from '../../js/multiple-choice-session.js';
import {date} from '../services/format.js';
import {useLifetime} from '../composables/lifecycle.js';

const {deckId} = defineProps({deckId:String});
const {signal,active} = useLifetime();
const sessions = shallowRef(null), busy = ref(false), error = ref(false);
async function load() {
  if (sessions.value || busy.value) return;
  busy.value = true; error.value = false;
  try { sessions.value = await api('/decks/' + deckId + '/multiple-choice/sessions',{signal}); }
  catch { if (active()) error.value = true; }
  finally { busy.value = false; }
}
</script>
<template>
  <details class="session-history" @toggle="$event.target.open && load()">
    <summary>Multiple-Choice history <span v-if="sessions" class="muted" data-mc-history-count>({{ sessions.length }})</span></summary>
    <div data-mc-history>
      <p v-if="busy">Loading Multiple-Choice history…</p>
      <template v-else-if="error"><p role="status" class="muted">Couldn’t load Multiple-Choice history.</p><button type="button" class="secondary small flat-button" @click="load">Try again</button></template>
      <template v-else-if="sessions">
        <div v-if="sessions.length" class="panel"><ul class="history-list"><li v-for="session in sessions" :key="session.id">
          <div><p>{{ date(session.created_at) }} · <strong>{{ SESSION_LABELS[session.status] || session.status }}</strong></p><p class="muted">{{ session.answered }} of {{ session.progress.ready }} answered · {{ session.correct }} correct</p></div>
          <a class="button secondary small flat-button" :href="'#/multiple-choice/' + encodeURIComponent(session.id)">{{ session.status === 'completed' ? 'Summary' : ['active','preparing','failed'].includes(session.status) ? 'Open session' : 'Details' }}</a>
        </li></ul></div>
        <p v-else class="muted">Your Multiple-Choice sessions will appear here.</p>
      </template>
    </div>
  </details>
</template>
