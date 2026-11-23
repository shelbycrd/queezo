<script setup>
import {computed, onMounted, ref} from 'vue';
import {api} from '../../js/api.js';
import {avatars, avatarUrl, dateTime, visibility} from '../services/profiles.js';
import {showNotice} from '../services/notice.js';
import {useLifetime} from '../composables/lifecycle.js';

const props = defineProps({profile:{type:Object,required:true}, mode:{type:String,required:true}});
const emit = defineEmits(['close','saved']);
const dialog = ref(), pending = ref(false), problem = ref(''), choicesError = ref(false);
const options = ref(null), limits = ref(props.profile);
const titles = {avatar:'Change profile picture',visibility:'Profile visibility',featured_deck_id:'Featured deck'};
const value = ref(props.profile[props.mode]);
const {signal,active} = useLifetime();
const unchanged = computed(() => value.value === limits.value[props.mode]);

onMounted(() => {
  dialog.value.showModal();
  if (props.mode === 'featured_deck_id') void loadOptions();
});
async function loadOptions() {
  choicesError.value = false;
  try { options.value = await api('/profiles/me/featured-options',{signal}); }
  catch { if (active()) choicesError.value = true; }
}
async function save() {
  if (pending.value || unchanged.value) return;
  pending.value = true;
  problem.value = '';
  try {
    const profile = await api('/profiles/me',{method:'PATCH',body:{[props.mode]:value.value},signal});
    if (!active()) return;
    emit('saved',profile);
    dialog.value.close();
    showNotice('Profile saved.',true);
  } catch (error) {
    if (!active()) return;
    problem.value = error.message;
    if (error.status === 429 && props.mode === 'avatar') {
      try { limits.value = await api('/profiles/me',{signal}); } catch { /* Keep the save error visible. */ }
      if (!limits.value.avatar_changes_remaining) value.value = limits.value.avatar;
    }
  } finally {
    pending.value = false;
  }
}
</script>

<template>
  <Teleport to="body">
    <dialog ref="dialog" class="profile-dialog" aria-labelledby="edit-profile-title" @close="emit('close')" @cancel.prevent="!pending && dialog.close()">
      <form @submit.prevent="save">
        <div class="dialog-heading"><h2 id="edit-profile-title">{{ titles[mode] }}</h2><button type="button" class="secondary small flat-button" aria-label="Close editor" :disabled="pending" @click="dialog.close()">×</button></div>
        <fieldset v-if="mode === 'avatar'" :disabled="pending" class="profile-avatar-options">
          <legend class="sr-only">Profile picture</legend>
          <p class="hint">{{ limits.avatar_changes_remaining ? limits.avatar_changes_remaining + ' of 10 changes available this hour.' : 'Next change: ' + dateTime(limits.avatar_next_change_at) }}</p>
          <div class="profile-avatar-picker">
            <label v-for="avatar in avatars" :key="avatar"><input v-model="value" class="sr-only" type="radio" name="profile-avatar" :value="avatar" :disabled="!limits.avatar_changes_remaining && avatar !== limits.avatar"><img :src="avatarUrl(avatar)" alt="" width="64" height="64"><span>{{ avatar[0].toUpperCase() + avatar.slice(1) }}</span></label>
          </div>
        </fieldset>
        <div v-else-if="mode === 'visibility'"><label for="profile-visibility">Who can see your profile?</label><select id="profile-visibility" v-model="value" :disabled="pending" aria-describedby="profile-visibility-info">
          <option value="public">Public</option><option value="unlisted">Unlisted</option><option value="private">Private</option></select>
          <p id="profile-visibility-info" class="hint">{{ visibility[value] }} This setting doesn’t change deck visibility.</p>
        </div>
        <div v-else><label for="profile-feature">Featured public deck</label><select id="profile-feature" v-model="value" :disabled="pending || !options">
          <option :value="null">No featured deck</option><option v-for="deck in options" :key="deck.id" :value="deck.id">{{ deck.title }}</option></select>
          <p v-if="choicesError" class="hint">Deck options couldn’t load. <button class="secondary small flat-button" type="button" @click="loadOptions">Retry</button></p>
          <p v-else-if="!options" class="hint" role="status">Loading public decks…</p>
        </div>
        <p v-if="problem" class="settings-error" role="alert">{{ problem }}</p>
        <div class="actions"><button type="submit" :disabled="pending || unchanged">{{ pending ? 'Saving…' : mode === 'avatar' ? 'Save picture' : 'Save' }}</button><button type="button" class="secondary flat-button" :disabled="pending" @click="dialog.close()">Cancel</button></div>
      </form>
    </dialog>
  </Teleport>
</template>
