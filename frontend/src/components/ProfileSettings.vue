<script setup>
import {computed, inject, nextTick, onMounted, ref} from 'vue';
import {api} from '../../js/api.js';
import {icon} from '../../js/icons.js';
import {useLifetime} from '../composables/lifecycle.js';
import {dateTime} from '../services/profiles.js';
import {account} from '../services/session.js';
import {showNotice} from '../services/notice.js';

const props = defineProps({profile:{type:Object,required:true}});
const emit = defineEmits(['close','saved']);
const auth = inject('auth'), {active,signal} = useLifetime();
const dialog = ref(), form = ref(), field = ref(''), pending = ref(false), problem = ref('');
const name = ref(''), current = ref(''), replacement = ref(''), confirm = ref('');
const nameLocked = computed(() => Date.parse(props.profile.display_name_next_change_at) > Date.now());
const maskedEmail = computed(() => {
  const [first,...rest] = account.value?.email || '';
  return first ? first + '*'.repeat(rest.length) : '—';
});
onMounted(() => dialog.value.showModal());

function edit(value) {
  field.value = value;
  name.value = props.profile.display_name;
  current.value = replacement.value = confirm.value = problem.value = '';
  if (value) void nextTick(() => form.value?.querySelector('input')?.focus());
}
async function save() {
  if (pending.value) return;
  pending.value = true;
  problem.value = '';
  try {
    if (field.value === 'name') {
      const updated = await api('/profiles/me',{method:'PATCH',body:{display_name:name.value},signal});
      if (!active()) return;
      emit('saved',updated);
      if (active()) showNotice('Display name saved.',true);
    } else {
      if (replacement.value !== confirm.value) {
        problem.value = 'Passwords do not match.';
        return;
      }
      await auth.changePassword({current_password:current.value,new_password:replacement.value,confirm_password:confirm.value});
      if (active()) showNotice('Password changed.',true);
    }
    if (active()) edit('');
  } catch (error) {
    if (active()) problem.value = error.message;
  } finally {
    pending.value = false;
  }
}
</script>

<template>
  <Teleport to="body">
    <dialog ref="dialog" class="profile-dialog profile-settings" aria-labelledby="profile-settings-heading"
      @close="emit('close')" @cancel.prevent="!pending && dialog.close()">
      <div class="dialog-heading"><h2 id="profile-settings-heading">Settings</h2><button type="button" class="secondary small flat-button" aria-label="Close settings" :disabled="pending" @click="dialog.close()">×</button></div>
      <dl class="profile-settings-rows">
        <div><dt>Display Name</dt><dd>{{ profile.display_name }}<small v-if="nameLocked" class="muted">Next edit {{ dateTime(profile.display_name_next_change_at) }}</small></dd>
          <dd><button type="button" class="secondary flat-button profile-edit-icon" aria-label="Edit display name" :disabled="nameLocked || pending" @click="edit('name')" v-html="icon('edit')"></button></dd></div>
        <div><dt>Username</dt><dd class="muted">@{{ profile.username }}</dd></div>
        <div><dt>Email</dt><dd class="profile-email"><span>{{ maskedEmail }}</span><small class="profile-verification" :class="{verified:account?.email_verified}">{{ account?.email_verified ? '✔ Verified' : 'Unverified' }}</small></dd></div>
        <div><dt>Password</dt><dd>********</dd><dd><button type="button" class="secondary flat-button profile-edit-icon" aria-label="Edit password" :disabled="pending" @click="edit('password')" v-html="icon('edit')"></button></dd></div>
      </dl>

      <form v-if="field" ref="form" class="profile-settings-form" @submit.prevent="save">
        <fieldset :disabled="pending">
          <legend>{{ field === 'name' ? 'Edit display name' : 'Change password' }}</legend>
          <template v-if="field === 'name'">
            <label for="settings-display-name">New display name</label><input id="settings-display-name" v-model="name" maxlength="80" required>
          </template>
          <template v-else>
            <label for="settings-current-password">Current password</label><input id="settings-current-password" v-model="current" required type="password" maxlength="1024" autocomplete="current-password">
            <label for="settings-new-password">New password</label><input id="settings-new-password" v-model="replacement" required type="password" minlength="11" maxlength="1024" autocomplete="new-password">
            <label for="settings-confirm-password">Confirm new password</label><input id="settings-confirm-password" v-model="confirm" required type="password" minlength="11" maxlength="1024" autocomplete="new-password">
          </template>
        </fieldset>
        <p v-if="problem" class="settings-error" role="alert">{{ problem }}</p>
        <div class="actions"><button type="submit" class="small" :disabled="pending">{{ pending ? 'Saving…' : 'Save' }}</button><button type="button" class="secondary small flat-button" :disabled="pending" @click="edit('')">Cancel</button></div>
      </form>
    </dialog>
  </Teleport>
</template>
