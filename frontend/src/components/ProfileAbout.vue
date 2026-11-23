<script setup>
import {computed, nextTick, ref} from 'vue';
import {api} from '../../js/api.js';
import {icon} from '../../js/icons.js';
import {useLifetime} from '../composables/lifecycle.js';
import {showNotice} from '../services/notice.js';

const {profile} = defineProps({profile:{type:Object,required:true}});
const emit = defineEmits(['saved']);
const {active,signal} = useLifetime();
const editing = ref(''), bio = ref(''), tags = ref([]), query = ref('');
const bioField = ref(), interestField = ref(), pending = ref(false);
const suggestionsOpen = ref(false), selectedIndex = ref(-1);
const bioLength = computed(() => Array.from(bio.value).length);
const suggestions = computed(() => {
  const term = query.value.trim().toLowerCase();
  if (!term || tags.value.length >= 5 || !suggestionsOpen.value) return [];
  return (profile.interests || [])
    .filter(tag => !tags.value.includes(tag) && tag.toLowerCase().includes(term)).slice(0,8);
});

function begin(section) {
  if (pending.value) return;
  editing.value = section;
  bio.value = profile.bio;
  tags.value = [...profile.interest_tags];
  query.value = '';
  suggestionsOpen.value = false;
  selectedIndex.value = -1;
  void nextTick(() => (section === 'bio' ? bioField.value : interestField.value)?.focus());
}
function updateBio(event) {
  const value = Array.from(event.target.value).slice(0,128).join('');
  bio.value = value;
  if (value !== event.target.value) event.target.value = value;
}
function addInterest(tag) {
  if (!suggestions.value.includes(tag)) return;
  tags.value.push(tag);
  query.value = '';
  selectedIndex.value = -1;
  void nextTick(() => interestField.value?.focus());
}
function searchInterests(event) {
  query.value = event.target.value;
  selectedIndex.value = -1;
  suggestionsOpen.value = true;
}
function moveSelection(event) {
  if (event.key === 'Escape') {
    suggestionsOpen.value = false;
    return;
  }
  const {length} = suggestions.value;
  if (event.key === 'Enter') {
    event.preventDefault();
    if (selectedIndex.value >= 0) addInterest(suggestions.value[selectedIndex.value]);
  } else if (length && (event.key === 'ArrowDown' || event.key === 'ArrowUp')) {
    event.preventDefault();
    const step = event.key === 'ArrowDown' ? 1 : -1;
    selectedIndex.value = selectedIndex.value < 0 ? (step > 0 ? 0 : length - 1) : (selectedIndex.value + step + length) % length;
  }
}
async function save() {
  if (pending.value || (editing.value === 'bio' && bioLength.value > 128)) return;
  pending.value = true;
  const body = editing.value === 'bio' ? {bio:bio.value} : {interest_tags:tags.value};
  try {
    const updated = await api('/profiles/me',{method:'PATCH',body,signal});
    if (!active()) return;
    emit('saved',updated);
    editing.value = '';
    showNotice('Profile saved.',true);
  } catch (error) {
    if (active()) showNotice(error.message);
  } finally {
    pending.value = false;
  }
}
</script>

<template>
  <section class="panel profile-section">
    <div class="profile-section-heading"><h2>About Me</h2>
      <button v-if="profile.is_owner && editing !== 'bio'" type="button" class="secondary flat-button profile-edit-icon" aria-label="Edit About Me" :disabled="pending" @click="begin('bio')" v-html="icon('edit')"></button>
    </div>
    <form v-if="editing === 'bio'" @submit.prevent="save">
      <label class="sr-only" for="profile-bio">Bio</label>
      <textarea id="profile-bio" ref="bioField" :value="bio" rows="4" :disabled="pending" aria-describedby="profile-bio-count" @input="updateBio"></textarea>
      <p id="profile-bio-count" class="hint">{{ bioLength }} / 128 characters</p>
      <div class="actions"><button type="submit" class="small" :disabled="pending || bioLength > 128">Save</button><button type="button" class="secondary flat-button small" :disabled="pending" @click="editing = ''">Cancel</button></div>
    </form>
    <p v-else-if="profile.bio" class="profile-bio">{{ profile.bio }}</p><p v-else class="muted">No bio yet.</p>
  </section>
  <section class="panel profile-section">
    <div class="profile-section-heading"><h2>Interests</h2>
      <button v-if="profile.is_owner && editing !== 'interests'" type="button" class="secondary flat-button profile-edit-icon" aria-label="Edit interests" :disabled="pending" @click="begin('interests')" v-html="icon('edit')"></button>
    </div>
    <form v-if="editing === 'interests'" @submit.prevent="save">
      <ul class="profile-tags profile-tag-editor">
        <li v-for="(tag,index) in tags" :key="tag" class="badge">{{ tag }}<button type="button" class="flat-button profile-tag-remove" :aria-label="'Remove ' + tag" :disabled="pending" @click="tags.splice(index,1)">×</button></li>
        <li class="profile-interest-input">
          <label class="sr-only" for="profile-interest-query">Search interests</label>
          <input id="profile-interest-query" ref="interestField" :value="query" type="text" autocomplete="off"
            :disabled="pending || tags.length >= 5" :placeholder="tags.length >= 5 ? '5 interests added' : 'Add an interest…'"
            role="combobox" aria-autocomplete="list" :aria-expanded="Boolean(suggestions.length)" aria-controls="profile-interest-suggestions"
            :aria-activedescendant="suggestions[selectedIndex] ? 'interest-option-' + selectedIndex : undefined"
            @input="searchInterests" @focus="suggestionsOpen = true" @blur="suggestionsOpen = false" @keydown="moveSelection">
          <ul v-show="suggestions.length" id="profile-interest-suggestions" class="profile-interest-suggestions" role="listbox">
            <li v-for="(tag,index) in suggestions" :id="'interest-option-' + index" :key="tag" role="option" :aria-selected="index === selectedIndex"
              @pointerdown.prevent @click="addInterest(tag)">{{ tag }}</li>
          </ul>
        </li>
      </ul>
      <div class="actions"><button type="submit" class="small" :disabled="pending">Save</button><button type="button" class="secondary flat-button small" :disabled="pending" @click="editing = ''">Cancel</button></div>
    </form>
    <ul v-else-if="profile.interest_tags.length" class="profile-tags"><li v-for="tag in profile.interest_tags" :key="tag" class="badge">{{ tag }}</li></ul>
    <p v-else class="muted">No interests listed.</p>
  </section>
</template>
