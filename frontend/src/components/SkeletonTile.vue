<script setup>
// One deck tile placeholder. It reuses the real tile classes, so its width, cover height, padding and
// minimum height always follow DeckTile.vue (including the tablet and phone breakpoints).
defineProps({buttons: {type: Number, default: 2}});
</script>

<template>
  <div class="deck-tile sk-deck-tile">
    <div class="deck-card portrait-deck">
      <div class="deck-cover sk-cover"></div>
      <div class="deck-card-body">
        <span class="sk sk-line sk-deck-title"></span>
        <span class="sk sk-line sk-deck-count"></span>
        <div class="actions"><span v-for="n in buttons" :key="n" class="sk sk-btn sk-btn-small" :class="{'sk-btn-wide': n === buttons && buttons > 1}"></span></div>
      </div>
    </div>
  </div>
</template>
