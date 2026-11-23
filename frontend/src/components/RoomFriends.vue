<script setup>
import {computed, onScopeDispose, ref, watch} from 'vue';
import {api} from '../../js/api.js';
import {avatarUrl} from '../services/profiles.js';
import {showNotice} from '../services/notice.js';

const props = defineProps({path:String,revision:String,full:Boolean});
const open = ref(false), page = ref(1), data = ref(null), busy = ref(false), sending = ref(null), error = ref('');
const labels = {member:'Already Joined',invited:'Invited',full:'Unavailable',available:'Invite'};
const items = computed(() => data.value?.items || []);
let request, stopped = false;
async function load() {
  request?.abort();
  const controller = request = new AbortController();
  busy.value = true;
  error.value = '';
  try {
    const snapshot = await api(props.path + '/friends?page=' + page.value,{signal:controller.signal});
    if (!controller.signal.aborted) data.value = snapshot;
  } catch (failure) {
    if (!controller.signal.aborted) error.value = failure.message;
  } finally {
    if (request === controller) busy.value = false;
  }
}
watch([open,page,() => props.revision], ([visible]) => {
  if (visible) void load();
  else request?.abort();
});
onScopeDispose(() => { stopped = true; request?.abort(); });

async function send(friend) {
  if (sending.value || props.full || friend.status !== 'available') return;
  sending.value = friend.username;
  try {
    await api(props.path + '/invite',{method:'POST',body:{username:friend.username}});
    if (!stopped) {
      if (data.value) data.value = {...data.value,items:items.value.map(item =>
        item.username === friend.username ? {...item,status:'invited'} : item)};
      showNotice('Study invitation sent.',true);
      if (open.value) void load();
    }
  } catch (failure) {
    if (!stopped) {
      showNotice(failure.message);
      if (open.value) void load();
    }
  } finally { sending.value = null; }
}
</script>

<template>
  <details class="room-invite-friends" @toggle="open = $event.currentTarget.open">
    <summary>Invite Friends</summary>
    <p v-if="error" role="status">{{ error }}</p>
    <p v-else-if="busy && !data" role="status">Loading friends…</p>
    <p v-else-if="!items.length" class="muted">No friends on this page.</p>
    <ul v-else aria-label="Friends to invite" :aria-busy="busy">
      <li v-for="friend in items" :key="friend.username" :class="{'is-unavailable':full || friend.status !== 'available'}">
        <img :src="avatarUrl(friend.avatar)" alt="" width="28" height="28">
        <strong>{{ friend.display_name }}</strong>
        <button type="button" class="secondary small flat-button" :disabled="Boolean(sending) || full || friend.status !== 'available'"
          :aria-label="(full && friend.status === 'available' ? 'Unavailable' : labels[friend.status]) + ' · ' + friend.display_name"
          @click="send(friend)">{{ sending === friend.username ? 'Sending…' : full && friend.status === 'available' ? 'Unavailable' : labels[friend.status] }}</button>
      </li>
    </ul>
    <nav v-if="page > 1 || data?.has_next" class="room-invite-pages" aria-label="Friends pages">
      <button type="button" class="secondary small flat-button" :disabled="page === 1 || busy" @click="page--">Previous</button>
      <span aria-live="polite">Page {{ page }}</span>
      <button type="button" class="secondary small flat-button" :disabled="busy || !data?.has_next" @click="page++">Next</button>
    </nav>
  </details>
</template>
