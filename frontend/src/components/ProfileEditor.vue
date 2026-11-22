<script setup>
import {computed, onMounted, reactive, ref} from 'vue';
import {api} from '../../js/api.js';
import {avatars, avatarUrl, dateTime, profileDraft, visibility} from '../services/profiles.js';
import {showNotice} from '../services/notice.js';
import {useLifetime} from '../composables/lifecycle.js';
import {buttonFeedback as vButtonFeedback} from './ButtonFeedback.js';

const props = defineProps({profile:{type:Object,required:true}, avatarOnly:Boolean});
const emit = defineEmits(['close','saved']);
const dialog = ref(), pending = ref(false), problem = ref('');
const options = ref(null), choicesError = ref(false);
const limits = ref(props.profile);
const draft = reactive(profileDraft(props.profile));
const {signal, active} = useLifetime();
const nameLocked = computed(() => Date.parse(limits.value.display_name_next_change_at) > Date.now());
onMounted(() => { dialog.value.showModal(); if (!props.avatarOnly) void loadOptions(); });
async function loadOptions() {
  choicesError.value = false;
  try { options.value = await api('/profiles/me/featured-options',{signal}); }
  catch { if (active()) choicesError.value = true; }
}
async function save() {
  if (pending.value) return;
  pending.value = true; problem.value = '';
  try {
    const profile = await api('/profiles/me',{method:'PATCH',body:props.avatarOnly ? {avatar:draft.avatar} : profileDraft(draft)});
    if (active()) {
      emit('saved',profile);
      dialog.value.close();
      showNotice(props.avatarOnly ? 'Profile picture saved.' : 'Profile saved.',true);
    }
  } catch (error) {
    if (!active()) return;
    problem.value = error.message;
    if (error.status === 429) {
      try { limits.value = await api('/profiles/me',{signal}); } catch { /* Keep the save error visible. */ }
      if (nameLocked.value) draft.display_name = limits.value.display_name;
      if (!limits.value.avatar_changes_remaining) draft.avatar = limits.value.avatar;
    }
  } finally { pending.value = false; }
}
</script>
<template>
  <Teleport to="body">
    <dialog ref="dialog" v-button-feedback class="profile-dialog" aria-labelledby="edit-profile-title" @close="emit('close')" @cancel.prevent="!pending && dialog.close()">
      <form @submit.prevent="save">
        <div class="dialog-heading"><h2 id="edit-profile-title">{{ avatarOnly ? 'Change profile picture' : 'Edit Profile' }}</h2><button type="button" class="secondary small flat-button" aria-label="Close editor" :disabled="pending" @click="dialog.close()">×</button></div>
        <fieldset :disabled="pending" class="profile-edit-fields">
          <legend class="sr-only">Profile information</legend>
          <div v-if="!avatarOnly"><label for="profile-display-name">Display name</label><input id="profile-display-name" v-model="draft.display_name" maxlength="80" required :readonly="nameLocked" aria-describedby="display-name-limit">
            <p id="display-name-limit" class="hint">{{ nameLocked ? 'Next change: ' + dateTime(limits.display_name_next_change_at) : 'You can change your display name once every 14 days.' }}</p></div>
          <div v-if="!avatarOnly"><label for="profile-username-input">Username</label><input id="profile-username-input" :value="'@' + profile.username" readonly><p class="hint">Your username stays the same.</p></div>
          <div v-if="!avatarOnly"><label for="profile-bio">Bio</label><textarea id="profile-bio" v-model="draft.bio" maxlength="200" rows="3" aria-describedby="profile-bio-count"></textarea><p id="profile-bio-count" class="hint">{{ draft.bio.length }} / 200 characters</p></div>
          <fieldset v-if="!avatarOnly" class="profile-interest-options"><legend>Interests</legend><p class="hint">Choose up to five.</p>
            <label v-for="interest in profile.interests" :key="interest"><input v-model="draft.interest_tags" type="checkbox" :value="interest" :disabled="draft.interest_tags.length >= 5 && !draft.interest_tags.includes(interest)"> {{ interest }}</label>
          </fieldset>
          <fieldset class="profile-avatar-options"><legend>Profile picture</legend>
            <p class="hint">{{ limits.avatar_changes_remaining ? limits.avatar_changes_remaining + ' of 10 changes available this hour.' : 'Next change: ' + dateTime(limits.avatar_next_change_at) }}</p>
            <div class="profile-avatar-picker">
              <label v-for="avatar in avatars" :key="avatar"><input v-model="draft.avatar" type="radio" name="profile-avatar" :value="avatar" :disabled="!limits.avatar_changes_remaining && avatar !== draft.avatar"><img :src="avatarUrl(avatar)" alt="" width="64" height="64"><span>{{ avatar[0].toUpperCase() + avatar.slice(1) }}</span></label>
            </div>
          </fieldset>
          <div v-if="!avatarOnly"><label for="profile-visibility">Profile visibility</label><select id="profile-visibility" v-model="draft.visibility" aria-describedby="profile-visibility-info">
            <option value="public">Public</option><option value="unlisted">Unlisted</option><option value="private">Private</option></select>
            <p id="profile-visibility-info" class="hint">{{ visibility[draft.visibility] }} This setting doesn’t change deck visibility.</p>
          </div>
          <div v-if="!avatarOnly"><label for="profile-feature">Featured public deck</label><select id="profile-feature" v-model="draft.featured_deck_id" :disabled="!options">
            <option :value="null">No featured deck</option><option v-for="deck in options" :key="deck.id" :value="deck.id">{{ deck.title }}</option></select>
            <p v-if="choicesError" class="hint">Deck options couldn’t load. <button class="secondary small flat-button" type="button" @click="loadOptions">Retry</button></p>
            <p v-else-if="!options" class="hint" role="status">Loading public decks…</p>
          </div>
        </fieldset>
        <p v-if="problem" class="inline-error" role="alert">{{ problem }}</p>
        <div class="actions"><button type="submit" :disabled="pending || (avatarOnly && (!limits.avatar_changes_remaining || draft.avatar === limits.avatar))">{{ pending ? 'Saving…' : avatarOnly ? 'Save picture' : 'Save profile' }}</button><button type="button" class="secondary flat-button" :disabled="pending" @click="dialog.close()">Cancel</button></div>
      </form>
    </dialog>
  </Teleport>
</template>
