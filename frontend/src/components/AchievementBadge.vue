<script setup>
// Decorative medallion; the surrounding text names the achievement for assistive technology.
const {name, unlocked} = defineProps({name:{type:String,required:true}, unlocked:Boolean});
</script>

<template>
  <span class="achievement-badge" :class="['badge-' + name.replace('_','-'), {locked:!unlocked}]" aria-hidden="true">
    <svg viewBox="0 0 48 48" fill="none" stroke-linecap="round" stroke-linejoin="round">
      <circle class="badge-ring" cx="24" cy="24" r="21"/>
      <circle class="badge-face" cx="24" cy="24" r="17"/>
      <g v-if="name === 'deck_master'" class="badge-glyph">
        <rect x="14" y="15" width="15" height="19" rx="3" transform="rotate(-10 21 24)"/>
        <rect x="19" y="14" width="15" height="19" rx="3"/>
        <path d="m26.5 19 1.4 2.9 3.1.4-2.3 2.1.6 3.1-2.8-1.5-2.8 1.5.6-3.1-2.3-2.1 3.1-.4z" class="badge-fill"/>
      </g>
      <g v-else-if="name === 'studious'" class="badge-glyph">
        <path d="M13 17.5c3.8-1.4 7.5-.9 11 1.5 3.5-2.4 7.2-2.9 11-1.5V32c-3.8-1.4-7.5-.9-11 1.5-3.5-2.4-7.2-2.9-11-1.5z"/>
        <path d="M24 19v14.5"/>
        <path d="M28 12.5v-2m5 4 1.4-1.4M19.5 12.5v-2" class="badge-accent"/>
      </g>
      <g v-else-if="name === 'hoster'" class="badge-glyph">
        <circle cx="24" cy="21" r="4"/>
        <path d="M16.5 33c.8-4 3.8-6.5 7.5-6.5s6.7 2.5 7.5 6.5"/>
        <circle cx="15" cy="23.5" r="2.6"/><circle cx="33" cy="23.5" r="2.6"/>
        <path d="m20 13.5 2 2.2 2-3.2 2 3.2 2-2.2-.8 4h-6.4z" class="badge-fill"/>
      </g>
      <g v-else class="badge-glyph"><path d="m24 15 2.6 5.4 5.9.8-4.3 4.1 1 5.8-5.2-2.8-5.2 2.8 1-5.8-4.3-4.1 5.9-.8z"/></g>
    </svg>
    <span v-if="!unlocked" class="badge-lock"><svg viewBox="0 0 16 16" fill="none"><rect x="3.5" y="7" width="9" height="6.5" rx="1.5"/><path d="M5.5 7V5.5a2.5 2.5 0 0 1 5 0V7"/></svg></span>
  </span>
</template>
