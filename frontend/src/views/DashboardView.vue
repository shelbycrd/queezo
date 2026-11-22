<script setup>
import {computed, onScopeDispose, ref, watch} from 'vue';
import {api} from '../../js/api.js';
import {icon} from '../../js/icons.js';
import {openFriends} from '../services/friends.js';
import {useResource} from '../composables/lifecycle.js';
import DeckTile from '../components/DeckTile.vue';
import ResourceState from '../components/ResourceState.vue';

const {data, error} = useResource(signal => Promise.all(['/dashboard','/dashboard/activity','/community/decks'].map(path => api(path,{signal})))
  .then(([stats,activity,recent]) => ({stats,activity,recent:recent.slice(0,20)})));
const days = computed(() => {
  const activity = data.value.activity, today = new Date(activity.today + 'T00:00:00Z');
  return Array.from({length:7}, (_, i) => {
    const day = new Date(today);
    day.setUTCDate(day.getUTCDate() - 6 + i);
    const key = day.toISOString().slice(0,10);
    return {key, label:day.toLocaleDateString('en',{weekday:'narrow',timeZone:'UTC'}), studied:activity.active_days.includes(key)};
  });
});
const track = ref(), previous = ref(false), next = ref(false);
const observer = new ResizeObserver(update);
watch(track, element => { observer.disconnect(); if (element) observer.observe(element); update(); });
onScopeDispose(() => observer.disconnect());
function update() {
  const element = track.value;
  previous.value = Boolean(element && element.scrollLeft > 1);
  next.value = Boolean(element && element.scrollLeft + element.clientWidth < element.scrollWidth - 2);
}
function scroll(left) {
  track.value?.scrollBy({left,behavior:matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth'});
}
</script>
<template>
  <ResourceState v-if="!data" :error="error"/>
  <template v-else>
    <div class="page-heading"><div><h1>Home</h1></div></div>
    <section class="home-welcome"><div><h2>What will you<br>learn today?</h2><p>Pick up a card and take it<br>one small step at a time.</p><div class="actions"><a class="button" href="#/decks">Open flashcards <span v-html="icon('arrow')"></span></a></div></div><div class="welcome-cloud" aria-hidden="true"><img src="/assets/queezo-cloud.svg" alt="" width="170" height="170"></div></section>
    <section class="recent-section"><div class="section-heading"><div><h2>Community Decks</h2><p class="muted">Explore public decks.</p></div><div class="carousel-controls"><button type="button" id="recent-prev" class="icon-button secondary" aria-label="Previous decks" :disabled="!previous" @click="scroll(-300)">←</button><button type="button" id="recent-next" class="icon-button secondary" aria-label="Next decks" :disabled="!next" @click="scroll(300)">→</button></div></div>
      <div v-if="data.recent.length" class="recent-track" id="recent-track" ref="track" tabindex="0" aria-label="Community decks, newest first" @scroll="update"><DeckTile v-for="deck in data.recent" :key="deck.share_token" :deck="deck" shared/></div>
      <div v-else class="empty"><div class="empty-icon" v-html="icon('cards')"></div><h3>No community decks yet.</h3><p class="muted">Create a deck and choose Public to share it here.</p><a class="button secondary" href="#/decks">Create a deck</a></div>
    </section>
    <div class="home-lower"><section class="panel streak-panel"><div class="section-heading"><h2>Your study rhythm</h2></div><div class="streak-number">{{ data.activity.study_streak }}<span> day{{ data.activity.study_streak === 1 ? '' : 's' }} in a row</span></div><p class="muted">{{ data.activity.active_today ? 'You made time to learn today. Keep it going!' : 'A flashcard review or finished pomodoro keeps your streak going.' }}</p>
      <div class="study-week"><div v-for="day in days" :key="day.key" class="week-day" :class="{studied:day.studied}"><span>{{ day.label }}</span><span class="day-dot" :aria-label="day.key + ': ' + (day.studied ? 'studied' : 'no study recorded')">{{ day.studied ? '✓' : '·' }}</span></div></div>
      <div class="home-counts"><span><strong>{{ data.stats.deck_count }}</strong> decks</span><span><strong>{{ data.stats.card_count }}</strong> flashcards</span></div>
    </section><section class="panel friends-panel"><div class="section-heading"><h2>Your study circle</h2></div><button type="button" id="home-friends" class="secondary flat-button" @click="openFriends"><span v-html="icon('friends')"></span> Open friends</button></section></div>
  </template>
</template>
