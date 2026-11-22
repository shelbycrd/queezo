<script setup>
import {ref} from 'vue';
import {copyText} from '../services/notice.js';
const props = defineProps({value:String, disabled:Boolean});
const pending = ref(false);
async function copy() {
  if (pending.value || props.disabled) return;
  pending.value = true;
  try { await copyText(props.value); } finally { pending.value = false; }
}
</script>
<template>
  <button type="button" class="secondary small flat-button" :disabled="disabled || pending" @click="copy"><slot/></button>
</template>
