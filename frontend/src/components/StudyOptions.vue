<script setup>
import {computed, onMounted, ref} from 'vue';
import {useRouter} from 'vue-router';
import {api} from '../../js/api.js';
import {authenticatedUser} from '../../js/auth-state.js';
import {validateTiming, saveTiming} from '../../js/study-options.js';
import {showNotice} from '../services/notice.js';
import {studyRequest, closeStudyOptions, sharedMultipleChoiceRoute} from '../services/study-dialog.js';
import {buttonFeedback as vButtonFeedback} from './ButtonFeedback.js';

const {request} = defineProps({request:Object});
const router = useRouter(), dialog = ref();
const studyType = ref(request.mode), mode = ref('unlimited'), scope = ref('question'), amount = ref(30), pending = ref(false);
const accountId = authenticatedUser()?.id;
const rule = computed(() => scope.value === 'deck' ? 'When time runs out, the session ends.' :
  studyType.value === 'classic' ? 'When time runs out, the answer is revealed.' : 'When time runs out, the question is skipped.');
const active = () => studyRequest.value === request && dialog.value?.open && authenticatedUser()?.id === accountId;
onMounted(() => dialog.value.showModal());
async function submit() {
  if (pending.value) return;
  const multiple = studyType.value === 'multiple-choice';
  try {
    const timing = validateTiming(mode.value, scope.value, amount.value);
    if (request.token && !multiple) {
      if (!active()) return;
      const query = {type:studyType.value};
      if (timing.mode === 'timed') Object.assign(query,{timing:mode.value,scope:scope.value,amount:String(amount.value)});
      closeStudyOptions(true);
      await router.push({name:'shared-study',params:{token:request.token},query});
      return;
    }
    const options = {method:'POST'};
    if (multiple && timing.mode === 'timed') options.body = {scope:timing.scope, seconds:timing.seconds};
    pending.value = true;
    const path = request.token ? '/shared/decks/' + encodeURIComponent(request.token) + '/multiple-choice'
      : `/decks/${request.deckId}/${multiple ? 'multiple-choice' : 'study'}`;
    const session = await api(path, options);
    if (authenticatedUser()?.id !== accountId) return;
    if (!active()) {
      const exit = multiple ? `/multiple-choice/${session.id}/cancel` : `/study/${session.id}/exit`;
      void api(exit, {method:'POST'}).catch(() => {});
      return;
    }
    if (!multiple) saveTiming(session.id, timing);
    closeStudyOptions(true);
    await router.push(request.token ? sharedMultipleChoiceRoute(session.id, request.token)
      : `/${multiple ? 'multiple-choice' : 'study'}/${session.id}`);
  } catch (error) {
    if (active()) showNotice(multiple && !request.token && error.status === 0 ? 'Could not confirm the new session. Check Previous Session on your deck before trying again.' : error.message);
  } finally { pending.value = false; }
}
</script>
<template>
  <Teleport to="body">
    <dialog ref="dialog" v-button-feedback class="study-options-dialog" aria-labelledby="study-options-title" @close="closeStudyOptions()">
      <form id="study-options-form" novalidate @submit.prevent="submit"><div class="dialog-heading"><h2 id="study-options-title">How would you like to study?</h2><button type="button" class="secondary small flat-button" id="cancel-study-options" aria-label="Close study options" @click="dialog.close()">×</button></div><fieldset class="study-type"><legend>Study mode</legend><div class="study-type-grid"><label><input type="radio" name="studyType" v-model="studyType" value="classic"><span><strong>Classic Mode</strong><small>{{ request.token ? 'Reveal each answer at your own pace.' : 'Recall the answer and rate it.' }}</small></span></label><label><input type="radio" name="studyType" v-model="studyType" value="multiple-choice"><span><strong>Multiple-Choice Mode</strong><small>Pick from four answers.</small></span></label></div></fieldset><fieldset class="classic-timing"><legend class="sr-only">Study timing</legend><div class="study-mode-choices"><div class="study-mode-card"><label class="mode-selector"><input type="radio" name="mode" v-model="mode" value="unlimited"><span class="mode-art" aria-hidden="true">∞</span><strong>Unlimited time</strong></label></div><div class="study-mode-card"><label class="mode-selector"><input type="radio" name="mode" v-model="mode" value="timed"><span class="mode-art" aria-hidden="true">◷</span><strong>Time bounded</strong></label></div></div><div class="timed-options"><label>Apply limit to<select id="study-scope" name="scope" v-model="scope" :disabled="mode !== 'timed'" @change="amount = scope === 'question' ? 30 : 10"><option value="question">Per question</option><option value="deck">Entire deck</option></select></label><label><span id="time-amount-label">{{ scope === 'question' ? 'Seconds per question' : 'Minutes for the deck' }}</span><input name="amount" v-model="amount" :disabled="mode !== 'timed'" type="number" min="1" :max="scope === 'question' ? 3600 : 180" required></label><p class="hint" id="time-rule" :class="{'timing-inactive':mode !== 'timed'}">{{ rule }}</p></div></fieldset><p v-if="request.token" class="hint">This session will not appear in your history.</p><p id="study-options-error" class="inline-error" hidden></p><button class="start-learning" type="submit" :disabled="pending">Start studying</button></form>
    </dialog>
  </Teleport>
</template>
