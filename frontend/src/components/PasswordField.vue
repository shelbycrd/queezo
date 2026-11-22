<script setup>
import {ref} from 'vue';
defineOptions({inheritAttrs:false});
defineProps({label:String, id:String});
const model = defineModel({type:String});
const shown = ref(false);
const field = ref();
defineExpose({validate:message => field.value?.setCustomValidity(message)});
</script>
<template>
  <div class="password-control">
    <input :id="id" ref="field" v-model="model" :type="shown ? 'text' : 'password'" v-bind="$attrs">
    <button type="button" class="secondary small flat-button" :aria-label="(shown ? 'Hide ' : 'Show ') + label" :aria-controls="id" :aria-pressed="shown" @click="shown = !shown">{{ shown ? 'Hide' : 'Show' }}</button>
  </div>
</template>
