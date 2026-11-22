<script setup>
defineProps({error:String});
</script>
<template>
  <template v-if="error">
    <h1>Couldn’t load this page</h1>
    <p class="muted">Check the message above, or try refreshing the page.</p>
    <a class="button secondary" href="#/decks">Return to Flashcards</a>
  </template>
  <p v-else class="muted" role="status">Loading…</p>
</template>
