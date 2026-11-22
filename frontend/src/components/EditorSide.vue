<script setup>
const props = defineProps({side:String, label:String, placeholder:String, photo:String, disabled:Boolean});
const value = defineModel({type:String});
const emit = defineEmits(['photo','remove']);
</script>
<template>
  <section class="editor-side">
    <label :for="side">{{ label }}</label><textarea :id="side" :name="side" v-model="value" required maxlength="250" :placeholder="placeholder" :disabled="disabled"></textarea>
    <div class="editor-toolbar"><label class="photo-picker" :for="side + '-photo'">＋ Photo<input class="sr-only" type="file" :id="side + '-photo'" accept="image/png,image/jpeg,image/webp" :aria-label="'Add photo to ' + label.toLowerCase()" :disabled="disabled" @change="emit('photo',$event.target)"></label></div>
    <div :id="side + '-image-preview'" class="image-preview" :hidden="!photo"><template v-if="photo"><img class="card-photo" :src="photo" :alt="label + ' photo preview'"><button class="secondary small" type="button" @click="emit('remove')">Remove photo</button></template></div>
  </section>
</template>
