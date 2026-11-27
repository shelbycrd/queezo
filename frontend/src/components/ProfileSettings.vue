<script setup>
import {computed, inject, nextTick, onMounted, ref} from 'vue';
import {api} from '../../js/api.js';
import {icon} from '../../js/icons.js';
import {useLifetime} from '../composables/lifecycle.js';
import {dateTime} from '../services/profiles.js';
import {account} from '../services/session.js';
import {showNotice} from '../services/notice.js';
import {passwordChangeProblem} from '../services/password-change.js';
import PasswordField from './PasswordField.vue';

const props = defineProps({profile:{type:Object,required:true}});
const emit = defineEmits(['close','saved']);
const auth = inject('auth'), {active,signal} = useLifetime();
const dialog = ref(), form = ref(), field = ref(''), pending = ref(false), problem = ref('');
const name = ref(''), current = ref(''), replacement = ref(''), confirm = ref('');
const passwordPending = ref(false), passwordProblem = ref('');
const busy = computed(() => pending.value || passwordPending.value);
const nameLocked = computed(() => Date.parse(props.profile.display_name_next_change_at) > Date.now());
const maskedEmail = computed(() => {
  const [first,...rest] = account.value?.email || '';
  return first ? first + '*'.repeat(rest.length) : '—';
});
onMounted(() => dialog.value.showModal());

function edit(value) {
  field.value = value;
  name.value = props.profile.display_name;
  problem.value = '';
  if (value) void nextTick(() => form.value?.querySelector('input')?.focus());
}
async function save() {
  if (pending.value) return;
  pending.value = true;
  problem.value = '';
  try {
    const updated = await api('/profiles/me',{method:'PATCH',body:{display_name:name.value},signal});
    if (!active()) return;
    emit('saved',updated);
    showNotice('Display name saved.',true);
    edit('');
  } catch (error) {
    if (active()) problem.value = error.message;
  } finally {
    pending.value = false;
  }
}
async function changePassword() {
  if (passwordPending.value) return;
  passwordProblem.value = passwordChangeProblem({current:current.value, replacement:replacement.value, confirm:confirm.value});
  if (passwordProblem.value) return;
  passwordPending.value = true;
  try {
    // Success signs this browser out and opens the login page with a confirmation message.
    await auth.changePassword({current_password:current.value,new_password:replacement.value,confirm_password:confirm.value});
  } catch (error) {
    if (active()) passwordProblem.value = error.message;
  } finally {
    if (active()) { passwordPending.value = false; current.value = replacement.value = confirm.value = ''; }
  }
}
</script>

<template>
  <Teleport to="body">
    <dialog ref="dialog" class="profile-dialog profile-settings" aria-labelledby="profile-settings-heading"
      @close="emit('close')" @cancel.prevent="!busy && dialog.close()">
      <div class="dialog-heading"><h2 id="profile-settings-heading">Settings</h2><button type="button" class="secondary small flat-button" aria-label="Close settings" :disabled="busy" @click="dialog.close()">×</button></div>
      <dl class="profile-settings-rows">
        <div><dt>Display Name</dt><dd>{{ profile.display_name }}<small v-if="nameLocked" class="muted">Next edit {{ dateTime(profile.display_name_next_change_at) }}</small></dd>
          <dd><button type="button" class="secondary flat-button profile-edit-icon" aria-label="Edit display name" :disabled="nameLocked || pending" @click="edit('name')" v-html="icon('edit')"></button></dd></div>
        <div><dt>Username</dt><dd class="muted">@{{ profile.username }}</dd></div>
        <div><dt>Email</dt><dd class="profile-email"><span>{{ maskedEmail }}</span><small class="profile-verification" :class="{verified:account?.email_verified}">{{ account?.email_verified ? '✔ Verified' : 'Unverified' }}</small></dd></div>
      </dl>

      <form v-if="field" ref="form" class="profile-settings-form" @submit.prevent="save">
        <fieldset :disabled="pending">
          <legend>Edit display name</legend>
          <label for="settings-display-name">New display name</label><input id="settings-display-name" v-model="name" maxlength="80" required>
        </fieldset>
        <p v-if="problem" class="settings-error" role="alert">{{ problem }}</p>
        <div class="actions"><button type="submit" class="small" :disabled="pending">{{ pending ? 'Saving…' : 'Save' }}</button><button type="button" class="secondary small flat-button" :disabled="pending" @click="edit('')">Cancel</button></div>
      </form>

      <section class="profile-security" aria-labelledby="settings-security-heading">
        <h3 id="settings-security-heading">Security</h3>
        <form class="profile-settings-form profile-password-form" novalidate @submit.prevent="changePassword">
          <fieldset :disabled="passwordPending">
            <legend>Change Password</legend>
            <p id="settings-password-note" class="hint">After changing your password you are signed out on every device and need to log in again.</p>
            <label for="settings-current-password">Current Password</label>
            <PasswordField id="settings-current-password" v-model="current" label="current password" required maxlength="1024" autocomplete="current-password"/>
            <label for="settings-new-password">New Password</label>
            <PasswordField id="settings-new-password" v-model="replacement" label="new password" required minlength="11" maxlength="1024" autocomplete="new-password" aria-describedby="settings-password-rule"/>
            <p id="settings-password-rule" class="hint">11–1024 characters, different from your current password.</p>
            <label for="settings-confirm-password">Confirm New Password</label>
            <PasswordField id="settings-confirm-password" v-model="confirm" label="new password confirmation" required minlength="11" maxlength="1024" autocomplete="new-password"/>
          </fieldset>
          <p v-if="passwordProblem" class="settings-error" role="alert">{{ passwordProblem }}</p>
          <div class="actions"><button type="submit" class="small" :disabled="passwordPending">{{ passwordPending ? 'Changing…' : 'Change Password' }}</button></div>
        </form>
      </section>
    </dialog>
  </Teleport>
</template>
