<script setup>
import {ref} from 'vue';
import {useRouter} from 'vue-router';
import {api} from '../../js/api.js';
import {useLifetime} from '../composables/lifecycle.js';
import {roomPath} from '../services/rooms.js';
import RoomView from './RoomView.vue';

// Public URLs carry the short room code. The server resolves it for members only.
const {code} = defineProps({code:String});
const router = useRouter(), {signal, active} = useLifetime();
const room = ref(null), error = ref('');
(async () => {
  try {
    const found = await api('/rooms/resolve/' + encodeURIComponent(code),{signal});
    if (!active()) return;
    // Canonicalize legacy UUID links and lowercase codes to the uppercase code URL.
    if (found.code !== code) { await router.replace(roomPath(found.code)); return; }
    room.value = found;
  } catch (failure) { if (active()) error.value = failure.message; }
})();
</script>

<template>
  <RoomView v-if="room" :room-id="room.id"/>
  <section v-else class="room-page">
    <div class="panel"><p role="status">{{ error || 'Opening study room…' }}</p><a class="button secondary flat-button" href="/home">Return home</a></div>
  </section>
</template>
