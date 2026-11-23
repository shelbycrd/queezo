<script setup>
import {nextTick, ref, watch} from 'vue';
import {api} from '../../js/api.js';
import {useLifetime} from '../composables/lifecycle.js';
import {avatarUrl} from '../services/profiles.js';
import {showNotice} from '../services/notice.js';

const {messages,path,visible} = defineProps({messages:Array,path:String,visible:Boolean});
const {active,signal} = useLifetime();
const draft = ref(''), pending = ref(false), log = ref();

function latest() {
  if (log.value) log.value.scrollTop = log.value.scrollHeight;
}
watch(() => messages.at(-1)?.id, async () => {
  const element = log.value;
  const nearBottom = !element || element.scrollHeight - element.scrollTop - element.clientHeight < 48;
  if (nearBottom) { await nextTick(); latest(); }
}, {immediate:true});
watch(() => visible, async show => { if (show) { await nextTick(); latest(); } });

async function send() {
  const text = draft.value.trim();
  if (!text || pending.value) return;
  pending.value = true;
  try {
    await api(path + '/chat',{method:'POST',body:{text},signal});
    if (active() && draft.value.trim() === text) draft.value = '';
  } catch (failure) {
    if (active()) showNotice(failure.message);
  } finally { pending.value = false; }
}
function timestamp(value) {
  return new Date(value).toLocaleTimeString(undefined,{hour:'numeric',minute:'2-digit'});
}
</script>
<template>
  <ol ref="log" class="room-chat-log" aria-label="Chat messages" role="log" aria-live="polite">
    <li v-for="(message,index) in messages" :key="message.id" class="room-message"
      :class="{grouped:index > 0 && messages[index - 1].author.username === message.author.username}">
      <template v-if="index === 0 || messages[index - 1].author.username !== message.author.username">
        <img :src="avatarUrl(message.author.avatar)" alt="" width="30" height="30">
        <strong>{{ message.author.display_name }}</strong>
      </template>
      <time :datetime="message.created_at">{{ timestamp(message.created_at) }}</time>
      <p>{{ message.text }}</p>
    </li>
  </ol>
  <p v-if="!messages.length" class="hint">No messages yet.</p>
  <form class="room-chat-form" @submit.prevent="send">
    <label class="sr-only" for="room-chat-input">Chat message</label>
    <input id="room-chat-input" v-model="draft" maxlength="500" placeholder="Message the room…">
    <button type="submit" class="small" :disabled="pending || !draft.trim()">Send</button>
  </form>
</template>
