<script setup>
import {computed, nextTick, onScopeDispose, ref, watch} from 'vue';
import {api} from '../../js/api.js';
import {playAnswerSound, playRoomLockSound, preparePageSound} from '../../js/audio.js';
import {useEvent,useLifetime} from '../composables/lifecycle.js';
import AmbientShapes from '../components/AmbientShapes.vue';
import RoomLobbyAvatars from '../components/RoomLobbyAvatars.vue';
import CardContent from '../components/CardContent.vue';
import CopyButton from '../components/CopyButton.vue';
import DeckTile from '../components/DeckTile.vue';
import RoomFriends from '../components/RoomFriends.vue';
import RoomChat from '../components/RoomChat.vue';
import {avatarUrl} from '../services/profiles.js';
import {accuracy, remainingSeconds, roomApi,roomModes,roomSocketUrl} from '../services/rooms.js';
import {showNotice} from '../services/notice.js';

const {roomId} = defineProps({roomId:String});
const path = roomApi(roomId);
const {signal,active} = useLifetime();
const savingSettings = ref(false), settingsSaved = ref(false);
let settingsTimer, draftRevision, lastServerTime = -Infinity;
const room = ref(null), error = ref(''), pending = ref(false);
const terminal = ref(false), live = ref(false), clock = ref(Date.now()), clockOffset = ref(0);
const drawer = ref(''), leaveDialog = ref();
const mobileRoomLayout = matchMedia('(max-width: 760px)');
const participantToggle = ref(), chatToggle = ref(), participantClose = ref(), chatClose = ref();
const decks = ref([]), deckError = ref('');
const deckId = ref(null), mode = ref('collaborative'), seconds = ref(30);
const selectedDeck = computed(() => decks.value.find(deck => deck.id === deckId.value));
const deckTrack = ref(), hasPreviousDeck = ref(false), hasNextDeck = ref(false);
function trackDecks() {
  const track = deckTrack.value;
  hasPreviousDeck.value = Boolean(track && track.scrollLeft > 1);
  hasNextDeck.value = Boolean(track && track.scrollLeft + track.clientWidth < track.scrollWidth - 2);
}
watch(deckTrack, (track, _, cleanup) => {
  if (!track) return;
  const observer = new ResizeObserver(trackDecks);
  observer.observe(track);
  cleanup(() => observer.disconnect());
  trackDecks();
});
function browseDecks(direction) {
  const track = deckTrack.value;
  track?.scrollBy({left:direction * track.clientWidth * .85,
    behavior:matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth'});
}
const questionKey = computed(() => room.value?.session ? room.value.session.id + ':' + room.value.session.position : '');
const submitted = ref(null);
const locked = computed(() => room.value?.question?.selected_id || (submitted.value?.key === questionKey.value ? submitted.value.option : null));
watch(questionKey, () => { submitted.value = null; });
const answerAvatars = computed(() => {
  if (room.value?.phase === 'reveal') {
    return room.value.question?.responses ?? [];
  }
  return locked.value && me.value ? [{...me.value, option_id:locked.value}] : [];
});
const remaining = computed(() => remainingSeconds(room.value?.session?.deadline,clock.value + clockOffset.value));
const countdown = computed(() => Math.min(5, Math.max(1, remaining.value ?? 5)));
watch([questionKey, () => room.value?.phase, locked], ([key,phase,choice], [previousKey,previousPhase,previousChoice]) => {
  if (!choice || key !== previousKey || previousPhase !== 'question') return;
  if (!previousChoice) playRoomLockSound();
  if (phase === 'reveal' && room.value.question?.correct_id) {
    playAnswerSound(choice === room.value.question.correct_id, previousChoice ? 0 : .1);
  }
});
const scores = computed(() => Object.fromEntries((room.value?.leaderboard || []).map(row => [row.username,row.score])));
function updateRoom(state) {
  const serverTime = Date.parse(state.server_time);
  if (serverTime < lastServerTime) return;
  lastServerTime = serverTime;
  clockOffset.value = serverTime - Date.now();
  room.value = state;
  error.value = '';
}
function participantStatus(member) {
  if (!member.connected) return {kind:'disconnected',label:'Disconnected'};
  if (member.spectator) return {kind:'spectator',label:'Spectating'};
  if (room.value.phase !== 'lobby') return {kind:'neutral',label:''};
  return member.host ? {kind:'neutral',label:'Ready not required'}
    : member.ready ? {kind:'ready',label:'Ready'} : {kind:'waiting',label:'Not ready'};
}
const participants = computed(() => {
  const people = room.value?.participants || [];
  if (!room.value?.leaderboard) return people;
  const rank = new Map(room.value.leaderboard.map((entry,index) => [entry.username,index]));
  return [...people].sort((a,b) => (rank.get(a.username) ?? people.length) - (rank.get(b.username) ?? people.length));
});
const me = computed(() => room.value?.participants.find(member => member.you));
const settingsChanged = computed(() => room.value && (deckId.value !== (room.value.deck?.id ?? null) ||
  mode.value !== room.value.mode || seconds.value !== room.value.seconds));
const startReason = computed(() => {
  if (savingSettings.value) return 'Saving room settings…';
  if (settingsChanged.value) return 'Wait for the room settings to sync.';
  if (!room.value?.deck?.card_count) return 'Choose a deck with flashcards.';
  return room.value.readiness_blocker;
});
const friendRevision = computed(() => JSON.stringify([room.value?.invite_revision,room.value?.participants.map(member => member.username)]));
const optionsKey = computed(() => room.value ? JSON.stringify([room.value.deck?.id,room.value.mode,room.value.seconds]) : '');
function syncSettings() {
  if (!room.value) return;
  draftRevision = undefined;
  deckId.value = room.value.deck?.id ?? null;
  mode.value = room.value.mode;
  seconds.value = room.value.seconds;
}
watch(optionsKey, (_, previous) => {
  if (!savingSettings.value && !settingsTimer) syncSettings();
  if (previous && room.value?.phase === 'lobby' && !room.value.is_host) {
    showNotice('The host updated the room settings. Readiness was reset.');
  }
});

watch(() => room.value?.is_host, async host => {
  if (!host) return;
  try { decks.value = await api(path + '/decks',{signal}); }
  catch (failure) { if (active()) deckError.value = failure.message; }
});
function openDrawer(panel) {
  drawer.value = panel;
  void nextTick(() => (panel === 'participants' ? participantClose.value : chatClose.value)?.focus());
}
function closeDrawer() {
  const panel = drawer.value;
  drawer.value = '';
  void nextTick(() => (panel === 'participants' ? participantToggle.value : chatToggle.value)?.focus());
}
useEvent(mobileRoomLayout,'change',event => {
  if (!event.matches && drawer.value) closeDrawer();
});
useEvent(document,'keydown',event => {
  if (!drawer.value || leaveDialog.value?.open) return;
  if (event.key === 'Escape') {
    event.preventDefault();
    closeDrawer();
  }
  if (event.key !== 'Tab') return;
  const close = drawer.value === 'participants' ? participantClose.value : chatClose.value;
  const panel = close?.closest('.room-drawer');
  if (!panel) return;
  const buttons = [...panel.querySelectorAll('button:enabled, input:enabled, summary')]
    .filter(element => element.getClientRects().length && element.tabIndex >= 0);
  const edge = event.shiftKey ? buttons[0] : buttons.at(-1);
  if (!panel.contains(document.activeElement) || document.activeElement === edge) {
    event.preventDefault();
    (event.shiftKey ? buttons.at(-1) : buttons[0])?.focus();
  }
});
function requestLeave() {
  leaveDialog.value.showModal();
}
async function leaveRoom() {
  if (await act('leave',{action:'leave'})) {
    leaveDialog.value?.close();
    location.hash = '/dashboard';
  }
}
let fetching = false;
async function refresh() {
  if (fetching) return;
  fetching = true;
  try {
    const latest = await api(path,{signal});
    if (!live.value) updateRoom(latest);
    error.value = '';
  } catch (failure) {
    if (!active()) return;
    error.value = failure.message;
    if ([401,403,404].includes(failure.status)) {
      terminal.value = true;
      room.value = null;
      socket?.close();
      clearTimeout(reconnect);
    }
  } finally { fetching = false; }
}
async function act(action,body,method='POST') {
  if (pending.value) return false;
  pending.value = true;
  try {
    await api(path + '/' + action,{method,body,signal});
    if (!live.value && action !== 'leave') await refresh();
    return active();
  } catch (failure) {
    if (active()) showNotice(failure.message);
    return false;
  } finally { pending.value = false; }
}
async function saveSettings() {
  clearTimeout(settingsTimer);
  settingsTimer = null;
  if (!room.value?.is_host || room.value.phase !== 'lobby' || savingSettings.value || !settingsChanged.value) return;
  if (!Number.isInteger(seconds.value) || seconds.value < 10 || seconds.value > 120) {
    syncSettings();
    showNotice('Enter 10–120 seconds per question.');
    return;
  }
  savingSettings.value = true;
  settingsSaved.value = false;
  try {
    await api(path + '/settings',{method:'PATCH',signal,body:{
      deck_id:deckId.value,mode:mode.value,seconds:seconds.value,expected_revision:draftRevision ?? room.value.settings_revision,
    }});
    const latest = await api(path,{signal});
    if (active()) {
      updateRoom(latest);
      settingsSaved.value = true;
    }
  } catch (failure) {
    if (active()) {
      showNotice(failure.message);
      try { updateRoom(await api(path,{signal})); } catch { /* Restore the last confirmed settings. */ }
    }
  } finally {
    if (active()) syncSettings();
    savingSettings.value = false;
  }
}
function beginSettingsEdit() {
  if (!settingsChanged.value) draftRevision = room.value.settings_revision;
}
function changeDeck(id) {
  beginSettingsEdit();
  deckId.value = id;
  void saveSettings();
}
function changeMode(event) {
  beginSettingsEdit();
  mode.value = event.target.value;
  void saveSettings();
}
function changeTimer(event) {
  beginSettingsEdit();
  seconds.value = event.target.valueAsNumber;
  settingsSaved.value = false;
  clearTimeout(settingsTimer);
  if (Number.isInteger(seconds.value) && seconds.value >= 10 && seconds.value <= 120) {
    settingsTimer = setTimeout(saveSettings,300);
  } else settingsTimer = null;
}

async function answer(option) {
  if (room.value.phase !== 'question' || me.value.spectator || locked.value || pending.value || remaining.value === 0) return;
  preparePageSound();
  const {session} = room.value, key = questionKey.value;
  if (await act('answer',{session_id:session.id,position:session.position,option_id:option}) && key === questionKey.value) {
    submitted.value = {key,option};
  }
}
let socket, reconnect;
function connect() {
  if (terminal.value) return;
  if (!active()) return;
  socket = new WebSocket(roomSocketUrl(roomId,location.origin));
  socket.onmessage = event => {
    if (!active() || terminal.value) return;
    updateRoom(JSON.parse(event.data));
    live.value = true;
  };
  socket.onclose = () => {
    if (!active() || terminal.value) return;
    live.value = false;
    void refresh();
    reconnect = setTimeout(connect,1800);
  };
}
void refresh();
connect();
const ticker = setInterval(() => { clock.value = Date.now(); },250);
onScopeDispose(() => { socket?.close(); clearTimeout(reconnect); clearTimeout(settingsTimer); clearInterval(ticker); });
</script>

<template>
  <section class="room-page">
    <div v-if="!room" class="panel"><p role="status">{{ error || 'Opening study room…' }}</p><a class="button secondary flat-button" href="/#/dashboard">Return home</a></div>
    <template v-else>
      <button v-if="drawer" class="room-drawer-scrim" type="button" tabindex="-1" aria-label="Close room drawer" @click="closeDrawer"></button>
      <div class="room-layout">
        <div class="room-main" :inert="Boolean(drawer)">
          <header class="panel room-heading">
            <div><div class="room-heading-title"><h1>{{ participants.find(member => member.host)?.display_name || 'Study' }}'s Room</h1><span class="badge room-code">{{ room.code }}</span><CopyButton :value="room.code">Copy code</CopyButton></div>
              <p>{{ roomModes[room.mode] }} Session</p></div>
            <div class="room-heading-actions"><small v-if="!live" class="room-connection" role="status">Reconnecting…</small>
              <button type="button" class="danger flat-button room-leave" @click="requestLeave"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M11 4H5v16h6m2-8h8m-3-3 3 3-3 3"/></svg>Leave Room</button></div>
          </header>
          <div class="room-mobile-actions">
            <button ref="participantToggle" type="button" class="secondary flat-button small" aria-controls="room-participants" :aria-expanded="drawer === 'participants'" @click="openDrawer('participants')">Participants</button>
            <button ref="chatToggle" type="button" class="secondary flat-button small" aria-controls="room-chat" :aria-expanded="drawer === 'chat'" @click="openDrawer('chat')">Chat</button>
          </div>
          <section class="panel room-study">
            <AmbientShapes/>
            <template v-if="room.phase === 'lobby'">
              <div v-if="room.is_host" class="room-setup">
                <div class="room-setup-scroll">
                  <h2>Lobby</h2>
                  <p v-if="room.deck" class="room-current-deck"><strong>{{ room.deck.title }}</strong> · {{ room.deck.card_count }} {{ room.deck.card_count === 1 ? 'flashcard' : 'flashcards' }}</p>
                  <p v-else class="muted">Choose a deck for this session.</p>
                  <section class="room-deck-selector" aria-labelledby="room-deck-heading">
                    <div class="room-deck-heading"><h3 id="room-deck-heading">Study deck</h3><div class="room-deck-arrows">
                      <button type="button" class="secondary flat-button" aria-label="Previous decks" :disabled="!hasPreviousDeck" @click="browseDecks(-1)">‹</button>
                      <button type="button" class="secondary flat-button" aria-label="Next decks" :disabled="!hasNextDeck" @click="browseDecks(1)">›</button>
                    </div></div>
                    <div v-if="decks.length" ref="deckTrack" class="room-deck-track" aria-label="Available study decks" tabindex="0" @scroll="trackDecks">
                      <DeckTile v-for="deck in decks" :key="deck.id" :deck="deck" selectable :selected="deckId === deck.id" :selection-disabled="savingSettings || pending" @select="changeDeck(deck.id)"/>
                    </div>
                    <p v-else-if="deckError" role="alert">{{ deckError }}</p>
                    <p v-else class="muted">No decks available to select.</p>
                  </section>
                  <p v-if="selectedDeck && selectedDeck.visibility !== 'public'" class="hint room-deck-access">Invited members can study this deck in this room.</p>
                  <div class="room-mode-settings">
                    <label for="room-mode">Study mode</label><select id="room-mode" :value="mode" :disabled="savingSettings || pending" @change="changeMode"><option value="collaborative">Collaborative</option><option value="challenge">Challenge</option></select>
                    <template v-if="mode === 'challenge'"><label for="room-seconds">Seconds per question</label><input id="room-seconds" :value="Number.isNaN(seconds) ? '' : seconds" type="number" min="10" max="120" :disabled="savingSettings || pending" @input="changeTimer" @change="saveSettings"></template>
                  </div>
                  <RoomLobbyAvatars :participants="participants" compact/>
                </div>
                <div class="room-lobby-footer">
                  <p v-if="startReason" id="room-start-reason" class="hint">{{ startReason }}</p>
                  <div class="actions"><button type="button" :disabled="pending || Boolean(startReason)" :aria-describedby="startReason ? 'room-start-reason' : undefined" @click="act('start')">Start study</button>
                    <small v-if="savingSettings || settingsSaved" class="muted" role="status">{{ savingSettings ? 'Saving…' : 'Saved' }}</small></div>
                </div>
              </div>
              <section v-else class="room-guest-lobby">
                <template v-if="room.deck">
                  <h2>Lobby</h2>
                  <div class="room-deck-preview"><DeckTile :deck="room.deck" preview/></div>
                  <p>{{ roomModes[room.mode] }}<span v-if="room.mode === 'challenge'"> · {{ room.seconds }} s per question</span></p>
                </template>
                <p class="room-waiting-label">Waiting for all connected participants except the host to be ready.</p>
                <RoomLobbyAvatars :participants="participants"/>
                <button v-if="me?.connected && !me.spectator" type="button" class="room-ready-button"
                  :disabled="pending" :aria-pressed="me.ready" @click="act('ready',{ready:!me.ready})">{{ me.ready ? 'Not Ready' : 'Ready' }}</button>
              </section>
            </template>
            <section v-else-if="room.phase === 'preparing' || room.phase === 'waiting'" class="room-loading" aria-live="polite">
              <h2>{{ room.phase === 'waiting' ? 'Loading the next question…' : 'Getting the session ready…' }}</h2>
            </section>
            <div v-else-if="room.phase === 'countdown'" class="room-start-countdown" role="timer" aria-label="Study starts in">
              {{ countdown }}
            </div>
            <section v-else-if="room.question" class="room-round">
              <div class="room-round-header">
                <div class="room-round-heading"><h2>Question {{ room.session.position + 1 }} of {{ room.session.total }}</h2>
                  <div class="room-round-tools">
                    <strong v-if="room.phase === 'reveal'" class="room-review-clock" role="timer"
                      :aria-label="room.session.paused ? 'Next question timer paused' : 'Seconds until next question'">{{ room.session.paused ? 'Ⅱ' : remaining }}</strong>
                    <strong v-else-if="room.mode === 'challenge' && remaining !== null" class="study-clock room-clock" role="timer" aria-label="Time remaining">{{ remaining }}s</strong>
                    <button v-if="room.mode === 'collaborative' && room.is_host" class="secondary flat-button small room-review-toggle" :class="{'room-round-hidden':room.phase !== 'reveal'}" type="button" :aria-label="room.session.paused ? 'Resume review' : 'Pause review'" :disabled="pending || room.phase !== 'reveal'" @click="act('pause',{paused:!room.session.paused,session_id:room.session.id,position:room.session.position})">
                      <span aria-hidden="true">{{ room.session.paused ? '▶' : 'Ⅱ' }}</span>
                    </button>
                  </div>
                </div>
                <progress :value="room.session.position + (room.phase === 'reveal' ? 1 : 0)" :max="room.session.total" aria-label="Question progress"></progress>
                <p v-if="me.spectator" class="muted">Spectating until the next session.</p>
              </div>
              <div class="room-round-content">
                <article class="study-sheet mc-question room-question" :key="questionKey"><section class="study-question">
                  <CardContent :text="room.question.front" :image="room.question.front_image" alt="Question photo"/>
                  <img v-if="room.phase === 'reveal' && room.question.back_image" class="card-photo" :src="room.question.back_image" alt="Correct answer photo">
                </section></article>
              </div>
              <div class="room-round-controls">
                <div class="mc-options mc-choices room-options" aria-label="Answer choices" role="group">
                  <div v-for="option in room.question.options" :key="option.id" class="room-answer">
                    <div class="room-answer-avatars" aria-hidden="true">
                      <img v-for="player in answerAvatars.filter(player => player.option_id === option.id)" :key="player.username" :src="avatarUrl(player.avatar)" :title="player.display_name" alt="" width="32" height="32">
                    </div>
                    <button type="button" class="mc-option flat-button"
                      :aria-pressed="option.id === locked" :class="{'mc-locked':room.phase === 'question' && option.id === locked,'mc-correct':option.id === room.question.correct_id,'mc-incorrect':room.question.correct_id && room.question.selected_id === option.id && option.id !== room.question.correct_id}"
                      :disabled="room.phase !== 'question' || me.spectator || Boolean(locked) || pending || (room.mode === 'challenge' && remaining === 0)" @click="answer(option.id)">
                      <span class="mc-option-text">{{ option.text }}</span>
                    </button>
                  </div>
                </div>
              </div>
            </section>
            <p v-else-if="room.phase === 'question' || room.phase === 'reveal'" role="status">Access to this deck changed. The session is ending.</p>
            <section v-else-if="room.phase === 'results'">
              <h2>Session results</h2>
              <p v-if="room.session.failed">{{ room.session.failed }} questions could not be prepared.</p>
              <ol v-if="room.mode === 'challenge'" class="room-results"><li v-for="result in room.results" :key="result.username">{{ result.display_name }} · {{ result.score }} points · {{ accuracy(result) }}% accuracy ({{ result.correct }} / {{ result.questions }})</li></ol>
              <template v-else>
                <p v-if="room.results.length">Group accuracy {{ accuracy(room.results.reduce((total,row) => ({correct:total.correct + row.correct,questions:total.questions + row.questions}),{correct:0,questions:0})) }}%</p>
                <ul class="room-results"><li v-for="result in room.results" :key="result.username">{{ result.display_name }} · {{ result.correct }} / {{ result.questions }} correct · {{ accuracy(result) }}%</li></ul>
              </template>
              <button v-if="room.is_host" type="button" :disabled="pending" @click="act('lobby')">Return to lobby</button>
            </section>
            <p v-if="error" role="alert">{{ error }}</p>
          </section>
        </div>
        <div class="room-side">
        <aside id="room-participants" class="panel room-participants room-drawer" :role="drawer === 'participants' ? 'dialog' : undefined" :aria-modal="drawer === 'participants' || undefined" aria-label="Participants" :class="{'drawer-open':drawer === 'participants'}">
          <div class="room-panel-heading"><h2>Participants <small>{{ room.participants.length }} / {{ room.capacity }}</small></h2><button ref="participantClose" type="button" class="secondary flat-button small room-drawer-close" aria-label="Close participants" @click="closeDrawer">×</button></div>
          <p v-if="room.phase === 'lobby'" class="room-ready-count muted" aria-live="polite">{{ room.readiness.ready }} of {{ room.readiness.total }} guests ready</p>
          <ul class="room-member-list">
            <li v-for="member in participants" :key="member.username">
              <img :src="avatarUrl(member.avatar)" width="34" height="34" alt="">
              <div class="room-member-text"><strong>{{ member.display_name }}</strong><span v-if="member.host" class="badge room-host-badge">Host</span>
                <small v-if="participantStatus(member).label" class="room-member-status" :class="'is-' + participantStatus(member).kind">{{ participantStatus(member).label }}</small></div>
              <span v-if="room.mode === 'challenge' && room.session && !member.spectator" class="room-score">{{ scores[member.username] ?? 0 }} pts</span>
            </li>
          </ul>
          <RoomFriends :path="path" :revision="friendRevision" :full="room.participants.length >= room.capacity"/>
        </aside>
        <aside id="room-chat" class="panel room-chat room-drawer" :role="drawer === 'chat' ? 'dialog' : undefined" :aria-modal="drawer === 'chat' || undefined" aria-label="Room Chat" :class="{'drawer-open':drawer === 'chat'}">
          <RoomChat :messages="room.chat || []" :path="path" :visible="drawer === 'chat'" :username="me?.username">
            <button ref="chatClose" type="button" class="secondary flat-button small room-drawer-close" aria-label="Close chat" @click="closeDrawer">×</button>
          </RoomChat>
        </aside>
        </div>
      </div>
      <dialog ref="leaveDialog" class="profile-dialog" aria-labelledby="leave-room-title" @cancel.prevent="!pending && leaveDialog.close()">
        <form @submit.prevent="leaveRoom">
          <div class="dialog-heading"><h2 id="leave-room-title">Leave study room?</h2></div>
          <p v-if="room.is_host">{{ room.participants.length > 1 ? 'The participant who joined first will become the host.' : 'The room will close when you leave.' }}</p>
          <p v-else>You’ll need a new invitation to rejoin after leaving.</p>
          <div class="actions">
            <button type="submit" :class="{'danger flat-button room-leave':!room.is_host}" :disabled="pending">Leave Room</button>
            <button type="button" class="secondary flat-button" :disabled="pending" @click="leaveDialog.close()">Cancel</button>
          </div>
        </form>
      </dialog>
    </template>
  </section>
</template>
