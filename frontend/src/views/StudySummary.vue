<script setup>
import {computed,ref} from 'vue';
import {api} from '../../js/api.js';
import {loadTiming} from '../../js/study-options.js';
import {chooseStudy} from '../services/study-dialog.js';
import {backIcon,duration} from '../services/format.js';
import {useResource} from '../composables/lifecycle.js';
import ResourceState from '../components/ResourceState.vue';

const {sessionId} = defineProps({sessionId:String});
const {data:summary,error} = useResource(signal => api('/study/' + sessionId + '/summary',{signal}));
const timing = loadTiming(sessionId), choosing = ref(false);
const stats = computed(() => {
  const s = summary.value;
  return [['Cards studied',s.total_unique_cards],['Total reviews',s.total_reviews],['Time together',duration(s.duration_seconds)],['Easy ratings',s.easy_count],['Normal ratings',s.normal_count],['Hard ratings',s.hard_count]];
});
async function again() {
  choosing.value = true;
  try { await chooseStudy(summary.value.deck_id); } finally { choosing.value = false; }
}
</script>
<template>
  <ResourceState v-if="!summary" :error="error"/>
  <template v-else>
    <a class="subpage-back" :href="'#/deck/' + summary.deck_id" aria-label="Go back" v-html="backIcon"></a>
    <div class="study-shell"><div class="summary-heading"><div class="check" aria-hidden="true">✓</div><p class="eyebrow">{{ summary.deck_title }}</p><h1>{{ summary.status === 'completed' ? 'Study session complete' : 'Study session ended' }}</h1>
      <p class="muted">{{ summary.status === 'completed' ? 'Every card has finished its reviews. A little more knowledge, a little more confidence.' : 'Your progress is saved in your session history.' }}</p></div>
      <p v-if="summary.status !== 'completed' && timing.scope === 'deck' && timing.deadline <= Date.now()" class="timed-session-ended">Your deck time limit was reached.</p>
      <div class="summary-grid"><div v-for="[label,value] in stats" :key="label" class="stat"><p class="muted">{{ label }}</p><div class="value">{{ value }}</div></div></div>
      <div class="actions summary-actions"><a class="button secondary" :href="'#/deck/' + summary.deck_id">Return to deck</a><button id="study-again" :disabled="choosing" @click="again">Study again →</button></div>
    </div>
  </template>
</template>
