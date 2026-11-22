<script setup>
import {computed, ref} from 'vue';
import {api} from '../../js/api.js';
import {highestStreak} from '../../js/profile-data.js';
import {soundsEnabled, setSoundsEnabled, playTimerPress} from '../../js/audio.js';
import {account} from '../services/session.js';
import {friendCount} from '../services/friends.js';
import {plural} from '../services/format.js';
import {useResource} from '../composables/lifecycle.js';
import DeckTile from '../components/DeckTile.vue';
import CopyButton from '../components/CopyButton.vue';
import ResourceState from '../components/ResourceState.vue';

const props = defineProps({section:String});
const resource = props.section === 'profile' ? useResource(signal => Promise.all(['/decks','/dashboard/activity','/friends'].map(path => api(path,{signal})))
  .then(([decks,activity,connections]) => ({
    count:decks.length, friends:connections.friends.length, best:highestStreak(activity.active_days),
    publicDecks:decks.filter(deck => deck.visibility === 'public').sort((a,b) => b.created_at.localeCompare(a.created_at) || b.id-a.id),
  }))) : {data:ref(null),error:ref('')};
const {data,error} = resource;
const enabled = ref(soundsEnabled());
const initial = computed(() => Array.from(account.value?.display_name.trim() || '')[0] || 'Q');
function soundSetting(event) {
  enabled.value = event.target.checked; setSoundsEnabled(enabled.value);
}
</script>
<template>
  <template v-if="section === 'profile'">
    <ResourceState v-if="!data" :error="error"/>
    <template v-else>
      <div class="page-heading"><h1>Profile</h1></div>
      <section class="panel profile-card" aria-label="Your profile">
        <div class="profile-avatar" aria-hidden="true">{{ initial }}</div>
        <div class="profile-identity"><h2>{{ account.display_name }}</h2><p class="profile-username">@{{ account.username }}</p>
          <dl class="profile-stats"><div><dt>Total Decks</dt><dd>{{ data.count }}</dd></div><div><dt>Friends</dt><dd data-friend-count>{{ friendCount ?? data.friends }}</dd></div><div><dt>Highest Streak</dt><dd>{{ data.best }}<span> {{ data.best === 1 ? 'day' : 'days' }}</span></dd></div></dl>
        </div>
        <div class="profile-actions"><a class="button" href="#/decks">Your decks</a><details class="profile-account"><summary>Account details</summary><dl class="profile-details"><dt>UID</dt><dd><span>{{ account.uid }}</span> <CopyButton :value="account.uid">Copy UID</CopyButton></dd><dt>Email</dt><dd><span>{{ account.email }}</span> <CopyButton :value="account.email">Copy email</CopyButton></dd></dl></details></div>
      </section>
      <section class="profile-public"><div class="section-heading"><h2>Public Decks</h2><span class="deck-total">{{ plural(data.publicDecks.length,'deck') }}</span></div>
        <div v-if="data.publicDecks.length" class="deck-grid"><DeckTile v-for="deck in data.publicDecks" :key="deck.id" :deck="deck"/></div>
        <div v-else class="empty"><h3>No public decks yet.</h3><p class="muted">Choose Public in a deck’s visibility settings to show it here.</p><a class="button secondary" href="#/decks">Manage decks</a></div>
      </section>
    </template>
  </template>
  <template v-else-if="section === 'help'"><div class="page-heading"><h1>Help</h1></div><div class="help-grid"><section class="panel"><h2>Flashcards</h2><p>Create a deck, then add a question and answer. Photos and lists are supported on both sides.</p><p>During study, press <kbd>Enter</kbd> to reveal. Use <kbd>1</kbd>, <kbd>2</kbd>, and <kbd>3</kbd> to rate Hard, Normal, or Easy and continue.</p><a href="#/decks">Open flashcards</a></section><section class="panel"><h2>GWA Calculator</h2><p>Enter 1–15 courses with units and grades. Subjects are optional. Type 175 for 1.75; Enter moves to the next course.</p><a href="#/gwa">Open calculator</a></section><section class="panel"><h2>Pomodoro</h2><p>Press the play icon to begin. Use pause to pause, Reset timer to restart the phase, or Skip to move on without study credit. Each next phase waits for play. Set durations under Timer settings, and add tasks with a pomodoro target.</p><a href="#/pomodoro">Open timer</a></section><section class="panel"><h2>Account access</h2><p>Create an account from the login page. Contact your administrator if you need help accessing an existing account.</p></section></div></template>
  <template v-else><div class="page-heading"><h1>Settings</h1></div><section class="panel account-page"><h2>Sound</h2><label class="setting-toggle"><span><strong>Study sounds</strong><small>Card page turns and Pomodoro play/pause keypress sounds.</small></span><input id="button-sounds" type="checkbox" :checked="enabled" @change="soundSetting"></label><p class="hint">Saved in this browser. Navigation remains silent.</p><button id="preview-sound" type="button" class="secondary small flat-button" :disabled="!enabled" @click="playTimerPress">Preview sound</button></section></template>
</template>
