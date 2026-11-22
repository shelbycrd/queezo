<script setup>
import {computed} from 'vue';
import {renderText, safeImageUrl} from '../../js/card-content.js';
const props = defineProps({text:String, image:String, alt:{type:String, default:'Flashcard photo'}, preview:Boolean});
const source = computed(() => safeImageUrl(props.image));
</script>
<template>
  <div class="formatted-content">
    <div v-if="preview" class="saved-text-preview" v-html="renderText(text)"></div>
    <template v-else><div class="formatted-text" v-html="renderText(text)"></div></template>
    <img v-if="source" class="card-photo" :src="source" :alt="alt" loading="lazy">
  </div>
</template>
