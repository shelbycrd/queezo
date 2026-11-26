<script setup>
import LoadingSkeleton from './LoadingSkeleton.vue';
defineProps({error:String, variant:{type:String, default:'page'}});
</script>
<template>
  <template v-if="error">
    <h1>Couldn’t load this page</h1>
    <p class="muted">Check the message above, or try refreshing the page.</p>
    <a class="button secondary" href="#/decks">Return to Flashcards</a>
  </template>
  <LoadingSkeleton v-else :variant="variant"/>
</template>
