<script setup>
import {onScopeDispose, ref, watch} from 'vue';
import {api} from '../../js/api.js';
import {account} from '../services/session.js';
import {roomApi,roomPath} from '../services/rooms.js';
import {showNotice} from '../services/notice.js';

const emit = defineEmits(['count','navigate']);
const data = ref(null);
const pending = ref(false);
let controller;
async function load() {
  if (!account.value || controller || document.hidden) return;
  const request = controller = new AbortController();
  try {
    const next = await api('/rooms',{signal:request.signal});
    if (!request.signal.aborted) {
      data.value = next;
      emit('count',next.invites.length,next.rooms.length);
    }
  } catch { /* The next poll can recover without interrupting study. */ }
  finally { if (controller === request) controller = null; }
}
watch(() => account.value?.id, () => {
  controller?.abort();
  controller = null;
  data.value = null;
  emit('count',0,0);
  void load();
}, {immediate:true});
const timer = setInterval(load,12000);
onScopeDispose(() => { clearInterval(timer); controller?.abort(); });

async function respond(id,accept) {
  if (pending.value) return;
  pending.value = true;
  try {
    await api(roomApi(id) + '/invitation',{method:'POST',body:{accept}});
    if (accept) {
      emit('navigate');
      location.href = roomPath(id);
    }
    controller?.abort();
    controller = null;
    void load();
  } catch (error) { showNotice(error.message); }
  finally { pending.value = false; }
}
</script>

<template>
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
