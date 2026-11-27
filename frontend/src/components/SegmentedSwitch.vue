<script setup>
import {nextTick, ref} from 'vue';

// Two or more mutually exclusive options as one pill: arrow keys move and select, like a radio group.
const props = defineProps({
  modelValue:{type:String,required:true}, options:{type:Array,required:true}, label:{type:String,required:true},
  disabled:Boolean,
});
const emit = defineEmits(['update:modelValue']);
const buttons = ref([]);

function choose(index, focus = false) {
  const option = props.options[index];
  if (!option || props.disabled) return;
  emit('update:modelValue', option.value);
  if (focus) void nextTick(() => buttons.value[index]?.focus());
}
function keydown(event) {
  const index = props.options.findIndex(option => option.value === props.modelValue), last = props.options.length - 1;
  const target = {ArrowRight:index + 1, ArrowDown:index + 1, ArrowLeft:index - 1, ArrowUp:index - 1, Home:0, End:last}[event.key];
  if (target === undefined) return;
  event.preventDefault();
  choose(Math.max(0, Math.min(last, target)), true);
}
</script>

<template>
  <div class="segmented" role="radiogroup" :aria-label="label" @keydown="keydown">
    <button v-for="(option, index) in options" :key="option.value" :ref="element => { buttons[index] = element; }" type="button"
      role="radio" :aria-checked="option.value === modelValue" :tabindex="option.value === modelValue ? 0 : -1" :disabled="disabled"
      @click="choose(index)">{{ option.label }}</button>
  </div>
</template>
