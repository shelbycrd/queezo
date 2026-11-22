<script setup>
import {ref} from 'vue';
import {soundsEnabled, setSoundsEnabled, playTimerPress} from '../../js/audio.js';
import {account} from '../services/session.js';
import CopyButton from '../components/CopyButton.vue';
defineProps({section:String});
const enabled = ref(soundsEnabled());
function soundSetting(event) {
  enabled.value = event.target.checked; setSoundsEnabled(enabled.value);
}
</script>
<template>
  <template v-if="section === 'help'"><div class="page-heading"><h1>Help</h1></div><div class="help-grid"><section class="panel"><h2>Flashcards</h2><p>Create a deck, then add a question and answer. Photos and lists are supported on both sides.</p><p>During study, press <kbd>Enter</kbd> to reveal. Use <kbd>1</kbd>, <kbd>2</kbd>, and <kbd>3</kbd> to rate Hard, Normal, or Easy and continue.</p><a href="#/decks">Open flashcards</a></section><section class="panel"><h2>GWA Calculator</h2><p>Enter 1–15 courses with units and grades. Subjects are optional. Type 175 for 1.75; Enter moves to the next course.</p><a href="#/gwa">Open calculator</a></section><section class="panel"><h2>Pomodoro</h2><p>Press the play icon to begin. Use pause to pause, Reset timer to restart the phase, or Skip to move on without study credit. Each next phase waits for play. Set durations under Timer settings, and add tasks with a pomodoro target.</p><a href="#/pomodoro">Open timer</a></section><section class="panel"><h2>Account access</h2><p>Create an account from the login page. Contact your administrator if you need help accessing an existing account.</p></section></div></template>
  <template v-else><div class="page-heading"><h1>Settings</h1></div><section class="panel account-page"><h2>Sound</h2><label class="setting-toggle"><span><strong>Study sounds</strong><small>Card page turns, answer feedback, and Pomodoro play/pause sounds.</small></span><input id="button-sounds" type="checkbox" :checked="enabled" @change="soundSetting"></label><p class="hint">Saved in this browser. Navigation remains silent.</p><button id="preview-sound" type="button" class="secondary small flat-button" :disabled="!enabled" @click="playTimerPress">Preview sound</button></section>
  <section v-if="account" class="panel account-page private-account-settings" aria-label="Account settings"><h2>Account Settings</h2><dl class="profile-details"><dt>UID</dt><dd>{{ account.uid }} <CopyButton :value="account.uid">Copy UID</CopyButton></dd><dt>Email</dt><dd>{{ account.email }} <CopyButton :value="account.email">Copy email</CopyButton></dd></dl></section></template>
</template>
