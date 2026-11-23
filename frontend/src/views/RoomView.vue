<script setup>
import {computed, nextTick, onScopeDispose, ref, watch} from 'vue';
import {api} from '../../js/api.js';
import {useEvent,useLifetime} from '../composables/lifecycle.js';
import CardContent from '../components/CardContent.vue';
import DeckTile from '../components/DeckTile.vue';
import RoomFriends from '../components/RoomFriends.vue';
import RoomChat from '../components/RoomChat.vue';
import {avatarUrl} from '../services/profiles.js';
import {accuracy, remainingSeconds, roomApi,roomModes,roomSocketUrl} from '../services/rooms.js';
import {showNotice} from '../services/notice.js';

const {roomId} = defineProps({roomId:String});
const path = roomApi(roomId);
const {signal,active} = useLifetime();
const room = ref(null), error = ref(''), pending = ref(false);
const terminal = ref(false), live = ref(false), selected = ref(null), clock = ref(Date.now()), clockOffset = ref(0);
const drawer = ref(''), leaveDialog = ref(), leaveStep = ref(0), leaveAction = ref('transfer'), successor = ref('');
const participantToggle = ref(), chatToggle = ref(), participantClose = ref(), chatClose = ref();
const decks = ref([]), deckError = ref('');
const deckId = ref(null), mode = ref('collaborative'), seconds = ref(30), sharePrivate = ref(false);
const questionKey = computed(() => room.value?.session ? room.value.session.id + ':' + room.value.session.position : '');
const submitted = ref(null);
const locked = computed(() => room.value?.question?.selected_id || (submitted.value?.key === questionKey.value ? submitted.value.option : null));
watch(questionKey, () => { selected.value = submitted.value = null; });
const remaining = computed(() => remainingSeconds(room.value?.session?.deadline,clock.value + clockOffset.value));
const scores = computed(() => Object.fromEntries((room.value?.leaderboard || []).map(row => [row.username,row.score])));
function updateRoom(state) {
  clockOffset.value = Date.parse(state.server_time) - Date.now();
  room.value = state;
  error.value = '';
}
const selectedDeck = computed(() => decks.value.find(deck => deck.id === deckId.value));
const participants = computed(() => {
  const people = room.value?.participants || [];
  if (!room.value?.leaderboard) return people;
  const rank = new Map(room.value.leaderboard.map((entry,index) => [entry.username,index]));
  return [...people].sort((a,b) => (rank.get(a.username) ?? people.length) - (rank.get(b.username) ?? people.length));
});
const me = computed(() => room.value?.participants.find(member => member.you));
const settingsChanged = computed(() => room.value && (deckId.value !== (room.value.deck?.id ?? null) ||
  mode.value !== room.value.mode || seconds.value !== room.value.seconds || sharePrivate.value !== Boolean(room.value.share_private)));
const canStart = computed(() => !settingsChanged.value && room.value?.deck?.card_count && !room.value.readiness_blocker);
const friendRevision = computed(() => JSON.stringify([room.value?.invite_revision,room.value?.participants.map(member => member.username)]));
const optionsKey = computed(() => room.value ? JSON.stringify([room.value.deck?.id,room.value.mode,room.value.seconds,room.value.share_private]) : '');
watch(optionsKey, () => {
  if (!room.value) return;
  deckId.value = room.value.deck?.id ?? null;
  mode.value = room.value.mode;
  seconds.value = room.value.seconds;
  sharePrivate.value = Boolean(room.value.share_private);
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
useEvent(document,'keydown',event => {
  if (drawer.value && event.key === 'Escape' && !leaveDialog.value?.open) closeDrawer();
});
function requestLeave() {
  leaveStep.value = 0;
  successor.value = '';
  leaveAction.value = 'transfer';
  leaveDialog.value.showModal();
}
async function leaveRoom() {
  const body = room.value.is_host ? {action:leaveAction.value,username:successor.value || null} : {action:'leave'};
  if (await act('leave',body)) {
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
function selectDeck(id) {
  if (deckId.value === id) return;
  deckId.value = id;
  sharePrivate.value = false;
}
function saveSettings() {
  return act('settings',{deck_id:deckId.value,mode:mode.value,seconds:seconds.value,share_private:sharePrivate.value},'PATCH');
}
function choose(option) {
  if (room.value.mode === 'challenge') selected.value = option;
  else void answer(option);
}
async function answer(option) {
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
onScopeDispose(() => { socket?.close(); clearTimeout(reconnect); clearInterval(ticker); });
</script>

<template>
  <section class="room-page">
    <div v-if="!room" class="panel"><p role="status">{{ error || 'Opening study room…' }}</p><a class="button secondary flat-button" href="/#/dashboard">Return home</a></div>
    <template v-else>
      <header class="panel room-heading"><div><h1>{{ room.name }} <small>{{ room.code }}</small></h1><p>{{ roomModes[room.mode] }}</p></div><button type="button" class="secondary flat-button" @click="requestLeave">Leave</button></header>
      <div class="room-mobile-actions">
        <button ref="participantToggle" type="button" class="secondary flat-button small" aria-controls="room-participants" :aria-expanded="drawer === 'participants'" @click="openDrawer('participants')">Participants</button>
        <button ref="chatToggle" type="button" class="secondary flat-button small" aria-controls="room-chat" :aria-expanded="drawer === 'chat'" @click="openDrawer('chat')">Chat</button>
      </div>
      <button v-if="drawer" class="room-drawer-scrim" type="button" tabindex="-1" aria-label="Close room drawer" @click="closeDrawer"></button>
      <div class="room-layout">
        <section class="panel room-study">
          <template v-if="room.phase === 'lobby'">
            <h2>Lobby</h2>
            <p v-if="room.deck">{{ room.deck.title }} · {{ room.deck.card_count }} questions</p>
            <p v-else class="muted">Waiting for the host to select a deck.</p>
            <form v-if="room.is_host" class="room-setup" @submit.prevent="saveSettings">
              <fieldset class="room-deck-selector">
                <legend>Study deck</legend>
                <div v-if="decks.length" class="room-deck-track" aria-label="Available study decks" tabindex="0">
                  <DeckTile v-for="deck in decks" :key="deck.id" :deck="deck" selectable :selected="deckId === deck.id"
                    @select="selectDeck(deck.id)"/>
                </div>
                <p v-else-if="!deckError" class="muted">No decks available to select.</p>
              </fieldset>
              <p v-if="deckError" role="alert">{{ deckError }}</p>
              <label v-if="selectedDeck && selectedDeck.visibility !== 'public'" class="room-check"><input v-model="sharePrivate" type="checkbox"> Allow invited room members to study this deck</label>
              <label for="room-mode">Study mode</label><select id="room-mode" v-model="mode"><option value="collaborative">Collaborative</option><option value="challenge">Challenge</option></select>
              <template v-if="mode === 'challenge'"><label for="room-seconds">Seconds per question</label><input id="room-seconds" v-model.number="seconds" type="number" min="10" max="120" required></template>
              <div class="actions"><button class="secondary flat-button" type="submit" :disabled="pending">Save settings</button><button type="button" :disabled="pending || !canStart" @click="act('start')">Start study</button></div>
            </form>
            <button v-else type="button" :disabled="pending" @click="act('ready',{ready:!me?.ready})">{{ me?.ready ? 'Not Ready' : 'Ready' }}</button>
            <p class="hint">{{ room.readiness_blocker || 'All connected participants are ready to start.' }}</p>
          </template>
          <section v-else-if="room.phase === 'preparing'" aria-live="polite">
            <h2>Preparing questions</h2>
            <p>{{ room.session.prepared }} / {{ room.session.total }} processed</p>
            <progress :value="room.session.prepared" :max="room.session.total" aria-label="Questions processed"></progress>
          </section>
          <template v-else-if="room.question">
            <div class="room-round-heading"><h2>Question {{ room.session.position + 1 }} of {{ room.session.total }}</h2><strong v-if="remaining !== null" role="timer">{{ remaining }}s</strong></div>
            <p v-if="me.spectator" class="muted">Spectating until the next session.</p>
            <CardContent :text="room.question.front" :image="room.question.front_image" alt="Question photo"/>
            <div class="mc-options room-options" aria-label="Answer choices" role="group">
              <button v-for="option in room.question.options" :key="option.id" type="button" class="mc-option flat-button"
                :aria-pressed="room.mode === 'challenge' ? option.id === (locked || selected) : undefined" :class="{'is-selected':room.phase === 'question' && option.id === (locked || selected),'mc-correct':option.id === room.question.correct_id,'mc-incorrect':room.question.correct_id && room.question.selected_id === option.id && option.id !== room.question.correct_id}"
                :disabled="room.phase !== 'question' || me.spectator || Boolean(locked) || pending || (room.mode === 'challenge' && remaining === 0)" @click="choose(option.id)">
                <span class="mc-option-text">{{ option.text }}</span>
              </button>
            </div>
            <button v-if="room.phase === 'question' && room.mode === 'challenge' && !me.spectator && !locked" type="button" :disabled="!selected || pending || remaining === 0" @click="answer(selected)">Lock In</button>
            <p v-if="room.phase === 'question' && locked" role="status">Answer locked. Waiting for other participants.</p>
            <div v-if="room.phase === 'reveal'">
              <button v-if="room.mode === 'collaborative' && room.is_host" class="secondary flat-button small" type="button" :disabled="pending" @click="act('pause',{paused:!room.session.paused})">{{ room.session.paused ? 'Resume' : 'Pause for discussion' }}</button>
              <p v-if="room.session.paused" role="status">Paused for discussion.</p>
              <img v-if="room.question.back_image" class="card-photo" :src="room.question.back_image" alt="Correct answer photo">
              <ol v-if="room.mode === 'challenge'" class="room-results" aria-label="Round leaderboard"><li v-for="result in room.leaderboard" :key="result.username">{{ result.display_name }} · {{ result.score }} points</li></ol>
              <p v-if="room.mode === 'collaborative'">{{ room.question.responses.filter(response => response.correct).length }} / {{ room.question.responses.length }} correct this round</p>
              <ul v-if="room.mode === 'collaborative'" class="room-results"><li v-for="response in room.question.responses" :key="response.username"><strong>{{ response.display_name }}</strong> · <template v-if="response.option_id">{{ room.question.options.find(option => option.id === response.option_id)?.text }} · {{ response.correct ? 'Correct' : 'Incorrect' }}</template><template v-else>No answer</template></li></ul>
            </div>
          </template>
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
          <p v-if="error" role="alert">{{ error }}</p><p v-else-if="!live" class="hint" role="status">Connecting to live updates…</p>
        </section>
        <div class="room-side">
        <aside id="room-participants" class="panel room-participants room-drawer" :class="{'drawer-open':drawer === 'participants'}">
          <div class="room-panel-heading"><h2>Participants <small>{{ room.participants.length }} / {{ room.capacity }}</small></h2><button ref="participantClose" type="button" class="secondary flat-button small room-drawer-close" aria-label="Close participants" @click="closeDrawer">×</button></div>
          <ul><li v-for="member in participants" :key="member.username">
            <img :src="avatarUrl(member.avatar)" width="36" height="36" alt="">
            <div><strong>{{ member.display_name }}</strong><small>{{ member.host ? 'Host · ' : '' }}{{ !member.connected ? 'Disconnected' : member.spectator ? 'Spectating' : room.phase === 'question' ? (member.answered ? 'Answered' : 'Answering') : member.host ? 'Ready not required' : member.ready ? 'Ready' : 'Not Ready' }}</small></div><span v-if="room.mode === 'challenge' && room.session && !member.spectator" class="room-score">{{ scores[member.username] ?? 0 }} pts</span>
          </li></ul>
          <RoomFriends :path="path" :revision="friendRevision" :full="room.participants.length >= room.capacity"/>
        </aside>
        <aside id="room-chat" class="panel room-chat room-drawer" :class="{'drawer-open':drawer === 'chat'}">
          <div class="room-panel-heading"><h2>Room Chat</h2><button ref="chatClose" type="button" class="secondary flat-button small room-drawer-close" aria-label="Close chat" @click="closeDrawer">×</button></div>
          <RoomChat :messages="room.chat || []" :path="path" :visible="drawer === 'chat'"/>
        </aside>
        </div>
      </div>
      <dialog ref="leaveDialog" class="profile-dialog" aria-labelledby="leave-room-title" @cancel.prevent="!pending && leaveDialog.close()">
        <form @submit.prevent="room.is_host && leaveStep === 0 ? leaveStep = 1 : leaveRoom()">
          <div class="dialog-heading"><h2 id="leave-room-title">Leave study room?</h2></div>
          <template v-if="room.is_host && leaveStep === 1">
            <fieldset :disabled="pending">
              <legend>Choose what happens to this room</legend>
              <label class="room-check"><input v-model="leaveAction" type="radio" value="transfer"> Transfer Host</label>
              <label class="room-check"><input v-model="leaveAction" type="radio" value="end"> End Room</label>
            </fieldset>
            <div v-if="leaveAction === 'transfer'">
              <label for="room-successor">New host</label><select id="room-successor" v-model="successor" required :disabled="pending">
                <option value="">Choose a connected participant</option>
                <option v-for="participant in participants.filter(person => !person.you && person.connected)" :key="participant.username" :value="participant.username">{{ participant.display_name }}</option>
              </select>
            </div>
            <p v-else class="hint">Ending the room closes it for everyone and expires pending invitations.</p>
          </template>
          <p v-else-if="room.is_host">You’re the host. Continue to transfer leadership or end the room.</p>
          <p v-else>You’ll need a new invitation to rejoin after leaving.</p>
          <div class="actions"><button type="submit" :disabled="pending || (room.is_host && leaveStep === 1 && leaveAction === 'transfer' && !successor)">{{ room.is_host ? (leaveStep === 0 ? 'Continue' : leaveAction === 'transfer' ? 'Transfer and leave' : 'End Room') : 'Leave Room' }}</button>
            <button type="button" class="secondary flat-button" :disabled="pending" @click="leaveDialog.close()">Cancel</button></div>
        </form>
      </dialog>
    </template>
  </section>
</template>
