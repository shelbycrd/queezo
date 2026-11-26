<script setup>
// Outline-only placeholder shown while content loads. Shapes are borders with no fill.
const props = defineProps({
  variant: {type: String, default: 'page'}, // page | grid | list | card | lines
  label: {type: String, default: 'Loading…'},
  count: {type: Number, default: 0},
});
const defaults = {page: 3, grid: 4, list: 3, card: 1, lines: 2};
const total = () => props.count || defaults[props.variant] || 3;
</script>

<template>
  <div class="skeleton" :class="'skeleton-' + variant" role="status" aria-live="polite" aria-busy="true">
    <span class="sr-only">{{ label }}</span>
    <div aria-hidden="true">
      <template v-if="variant === 'page'">
        <span class="sk sk-title"></span>
        <div class="sk sk-panel"><span v-for="n in total()" :key="n" class="sk sk-line" :style="{width: (92 - n * 14) + '%'}"></span></div>
        <div class="sk-grid"><span v-for="n in 3" :key="n" class="sk sk-tile"></span></div>
      </template>
      <div v-else-if="variant === 'grid'" class="sk-grid"><span v-for="n in total()" :key="n" class="sk sk-tile"></span></div>
      <div v-else-if="variant === 'list'" class="sk-list">
        <div v-for="n in total()" :key="n" class="sk sk-row"><span class="sk sk-dot"></span><span class="sk sk-line" :style="{width: (70 - n * 9) + '%'}"></span></div>
      </div>
      <div v-else-if="variant === 'card'" class="sk sk-card"><span class="sk sk-line sk-center" style="width:55%"></span><span class="sk sk-line sk-center" style="width:35%"></span></div>
      <div v-else class="sk-lines"><span v-for="n in total()" :key="n" class="sk sk-line" :style="{width: (85 - n * 20) + '%'}"></span></div>
    </div>
  </div>
</template>

