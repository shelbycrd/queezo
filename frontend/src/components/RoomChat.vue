<script setup>
import {nextTick, ref, watch} from 'vue';
import {api} from '../../js/api.js';
import {playChatPop, preparePageSound} from '../../js/audio.js';
import {useEvent,useLifetime} from '../composables/lifecycle.js';
import {avatarUrl} from '../services/profiles.js';
import {showNotice} from '../services/notice.js';

const {messages,path,visible,username} = defineProps({messages:Array,path:String,visible:Boolean,username:String});
const {active,signal} = useLifetime();
const draft = ref(''), pending = ref(false), log = ref();
let followLatest = true;
let lastMessage = messages.at(-1)?.id ?? 0;
function preference(name, value) {
  try {
    const key = 'queezo.room-chat.' + username + '.' + name;
    if (value !== undefined) localStorage.setItem(key,value ? 'yes' : 'no');
    return localStorage.getItem(key) === 'yes';
  } catch { return false; }
}
const accepted = ref(preference('accepted'));
const muted = ref(preference('muted'));
function enterChat() {
  accepted.value = true;
  preference('accepted',true);
  if (!muted.value) preparePageSound();
  void nextTick(() => {
    latest();
    document.getElementById('room-chat-input')?.focus();
  });
}
function toggleMute() {
  muted.value = !muted.value;
  preference('muted',muted.value);
  if (!muted.value) preparePageSound();
}
function unlockSound() {
  if (accepted.value && !muted.value) preparePageSound();
}
useEvent(document,'pointerdown',unlockSound);
useEvent(document,'keydown',unlockSound);
function updateFollow() {
  if (log.value?.clientHeight) followLatest = log.value.scrollHeight - log.value.scrollTop - log.value.clientHeight < 48;
}
function grouped(index) {
  return index > 0 && messages[index - 1].author.username === messages[index].author.username;
}

function latest() {
  if (log.value) log.value.scrollTop = log.value.scrollHeight;
}
watch(() => messages.at(-1)?.id, async () => {
  const incoming = messages.some(message => message.id > lastMessage && message.author.username !== username);
  lastMessage = Math.max(lastMessage,messages.at(-1)?.id ?? 0);
  if (incoming && accepted.value && !muted.value) playChatPop();
  if (followLatest) { await nextTick(); latest(); }
}, {immediate:true});
watch(() => visible, async show => { if (show && followLatest) { await nextTick(); latest(); } });

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
  <div class="room-panel-heading"><h2>Room Chat</h2><div class="room-chat-controls">
    <button v-if="accepted" type="button" class="secondary flat-button small" :aria-pressed="muted" @click="toggleMute">{{ muted ? 'Unmute' : 'Mute' }}</button>
    <slot/>
  </div></div>
  <div v-if="!accepted" class="room-chat-notice">
    <p>Messages are written by other users and may contain strong language. Be respectful and avoid sharing personal information.</p>
    <button type="button" class="small" @click="enterChat">Enter Chat</button>
  </div>
  <template v-else>
  <ol ref="log" class="room-chat-log" aria-label="Chat messages" role="log" aria-live="polite" @scroll="updateFollow">
    <li v-for="(message,index) in messages" :key="message.id" class="room-message" :class="{grouped:grouped(index)}">
      <img v-if="!grouped(index)" :src="avatarUrl(message.author.avatar)" alt="" width="24" height="24">
      <p><strong :class="{'sr-only':grouped(index)}">{{ message.author.display_name }}:</strong> {{ message.text }}
        <time :datetime="message.created_at">{{ timestamp(message.created_at) }}</time>
      </p>
    </li>
  </ol>
  <p v-if="!messages.length" class="hint">No messages yet.</p>
  <form class="room-chat-form" @submit.prevent="send">
    <label class="sr-only" for="room-chat-input">Chat message</label>
    <input id="room-chat-input" v-model="draft" maxlength="500" placeholder="Message the room…">
    <button type="submit" class="small" :disabled="pending || !draft.trim()">Send</button>
  </form>
  </template>
</template>
