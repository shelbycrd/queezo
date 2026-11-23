<script setup>
import {onMounted,ref} from 'vue';
import {api} from '../../js/api.js';
import {profileApi,reportReasons} from '../services/profiles.js';
import {showNotice} from '../services/notice.js';
import {useLifetime} from '../composables/lifecycle.js';
import {buttonFeedback as vButtonFeedback} from './ButtonFeedback.js';

const props = defineProps({username:String});
const emit = defineEmits(['close']);
const dialog = ref(), reason = ref(''), explanation = ref(''), pending = ref(false);
const {active} = useLifetime();
onMounted(() => dialog.value.showModal());
async function send() {
  if (pending.value) return;
  pending.value = true;;
  try {
    await api(profileApi(props.username) + '/reports',{method:'POST',body:{reason:reason.value,explanation:explanation.value}});
    if (!active()) return;
    dialog.value.close();
    showNotice('Report submitted for review.',true);
  } catch (failure) { if (active()) showNotice(failure.message); }
  finally { pending.value = false; }
}
</script>
<template>
  <Teleport to="body">
    <dialog ref="dialog" v-button-feedback class="profile-dialog" aria-labelledby="report-profile-title" @close="emit('close')" @cancel.prevent="!pending && dialog.close()">
      <form @submit.prevent="send">
        <div class="dialog-heading"><h2 id="report-profile-title">Report Profile</h2><button type="button" class="secondary small flat-button" aria-label="Close report profile" :disabled="pending" @click="dialog.close()">×</button></div>
        <p class="muted">Report @{{ username }} for review.</p>
        <label for="profile-report-reason">Reason</label><select id="profile-report-reason" v-model="reason" required :disabled="pending"><option disabled value="">Choose a reason</option><option v-for="(label,value) in reportReasons" :key="value" :value="value">{{ label }}</option></select>
        <label for="profile-report-details">Explanation (optional)</label><textarea id="profile-report-details" v-model="explanation" rows="3" maxlength="400" :disabled="pending"></textarea>
        <div class="actions"><button type="submit" :disabled="pending">{{ pending ? 'Submitting…' : 'Submit report' }}</button><button type="button" class="secondary flat-button" :disabled="pending" @click="dialog.close()">Cancel</button></div>
      </form>
    </dialog>
  </Teleport>
</template>
