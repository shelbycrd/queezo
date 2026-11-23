<script setup>
import {computed, nextTick, ref, watch} from 'vue';
import {notice, noticeDuration, showNotice} from '../services/notice.js';
import {buttonFeedback as vButtonFeedback} from './ButtonFeedback.js';
const popup = ref();
const host = ref('body');
const message = computed(() => notice.value);
watch(message, async (current, previous, cleanup) => {
  popup.value?.hidePopover?.();
  if (!current) return;
  host.value = document.querySelector('dialog[open]') || 'body';
  const modal = host.value;
  const close = () => { if (notice.value === current) showNotice(''); };
  modal?.addEventListener?.('close', close, {once:true});
  const timeout = setTimeout(close,noticeDuration);
  cleanup(() => {
    clearTimeout(timeout);
    modal?.removeEventListener?.('close', close);
  });
  await nextTick();
  if (notice.value !== current) return;
  popup.value?.showPopover?.();
});
</script>
<template>
  <Teleport :to="host">
    <div id="notice" ref="popup" v-button-feedback class="notice" :class="{success:message?.success}" :role="message?.success ? 'status' : 'alert'" :hidden="!message" popover="manual">
      <template v-if="message"><span>{{ message.message }}</span><button class="secondary flat-button" type="button" aria-label="Dismiss message" @click="showNotice('')">×</button></template>
    </div>
  </Teleport>
</template>
