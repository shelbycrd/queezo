<script setup>
import {ref, watch} from 'vue';
import {api} from '../../js/api.js';
import {account} from '../services/session.js';
import {roomApi,roomPath,roomSocketUrl} from '../services/rooms.js';
import {showNotice} from '../services/notice.js';
import {arrivedInvites} from '../services/rooms.js';
import {buttonFeedback as vButtonFeedback} from './ButtonFeedback.js';

const emit = defineEmits(['count','navigate']);
const data = ref(null);
const pending = ref(false);
const popup = ref(null);
let load, seen = null;
function apply(snapshot) {
  data.value = snapshot;
  emit('count',snapshot?.invites.length ?? 0,snapshot?.rooms.length ?? 0);
  const invites = snapshot?.invites ?? [];
  // The first snapshot is history; only invitations that arrive afterwards pop up.
  const arrived = seen ? arrivedInvites(seen,invites) : [];
  if (snapshot) seen = new Set(invites.map(invite => invite.room_id));
  if (arrived.length) popup.value = arrived[0];
  else if (popup.value && !invites.some(invite => invite.room_id === popup.value.room_id)) popup.value = null;
}

watch(() => account.value?.id, (id, _, cleanup) => {
  seen = null;
  apply(null);
  pending.value = false;
  if (!id) return;
  const lifetime = new AbortController();
  let socket, retry, fetching = false, live = false;

  const refresh = async () => {
    if (fetching || live || lifetime.signal.aborted) return;
    fetching = true;
    try {
      const snapshot = await api('/rooms',{signal:lifetime.signal});
      if (!live && !lifetime.signal.aborted) apply(snapshot);
    } catch { /* The socket will retry and recover the full notification list. */ }
    finally { fetching = false; }
  };

  function connect() {
    if (lifetime.signal.aborted) return;
    socket = new WebSocket(roomSocketUrl('notifications',location.origin));
    socket.onmessage = event => {
      if (lifetime.signal.aborted) return;
      live = true;
      apply(JSON.parse(event.data));
    };
    socket.onclose = () => {
      if (lifetime.signal.aborted) return;
      live = false;
      void refresh();
      retry = setTimeout(connect,1800);
    };
  }
  load = refresh;
  void refresh();
  connect();
  cleanup(() => {
    lifetime.abort();
    socket?.close();
    clearTimeout(retry);
    load = null;
  });
}, {immediate:true});

async function respond(id,accept) {
  const userId = account.value?.id;
  if (pending.value || !userId) return;
  pending.value = true;
  try {
    await api(roomApi(id) + '/invitation',{method:'POST',body:{accept}});
    if (account.value?.id !== userId) return;
    if (popup.value?.room_id === id) popup.value = null;
    if (data.value) apply({...data.value,invites:data.value.invites.filter(invite => invite.room_id !== id)});
    if (accept) {
      emit('navigate');
      location.href = roomPath(id);
    }
    void load?.();
  } catch (error) { if (account.value?.id === userId) showNotice(error.message); }
  finally { if (account.value?.id === userId) pending.value = false; }
}
</script>

<template>
  <Teleport to="body">
    <aside v-if="popup" v-button-feedback class="pomodoro-alert study-invite-alert" aria-label="Study invitation">
      <div role="status" aria-live="polite"><strong>Study invitation</strong><p>{{ popup.sender.display_name }} invited you to study.</p></div>
      <div class="actions">
        <button class="small" type="button" :disabled="pending" @click="respond(popup.room_id,true)">Accept</button>
        <button class="secondary flat-button small" type="button" :disabled="pending" @click="respond(popup.room_id,false)">Decline</button>
        <button class="secondary flat-button small" type="button" aria-label="Dismiss study invitation popup" @click="popup = null">×</button>
      </div>
    </aside>
  </Teleport>
  <section v-if="data?.invites.length" class="room-invitations" aria-label="Study room invitations">
    <h3>Study invitations</h3>
    <article v-for="invite in data.invites" :key="invite.room_id">
      <p>{{ invite.sender.display_name }} invited you to study.</p>
      <div class="actions">
        <button class="small" type="button" :disabled="pending" @click="respond(invite.room_id,true)">Accept</button>
        <button class="secondary flat-button small" type="button" :disabled="pending" @click="respond(invite.room_id,false)">Decline</button>
      </div>
    </article>
  </section>
  <section v-if="data?.rooms.length" class="room-invitations" aria-label="Your study rooms">
    <h3>Your study rooms</h3>
    <ul><li v-for="room in data.rooms" :key="room.id"><a :href="roomPath(room.id)" @click="emit('navigate')">Study Room {{ room.code }}</a></li></ul>
  </section>
</template>
