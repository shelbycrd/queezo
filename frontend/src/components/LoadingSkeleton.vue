<script setup>
import SkeletonTile from './SkeletonTile.vue';

// Outline-only placeholders shown while content loads. Each page variant is built from that page's own
// layout classes (page-heading, deck-grid, panel, profile-card, timetable, study-sheet, …) so the
// placeholder takes the same space as the finished content on desktop, tablet and phone.
const props = defineProps({
  // page | grid | track | list | friends | results | schedule-rows | card | lines
  // | decks | deck | shared-deck | home | profile | summary | study-card | schedule
  variant: {type: String, default: 'page'},
  label: {type: String, default: 'Loading…'},
  count: {type: Number, default: 0},
});
const defaults = {page: 3, grid: 6, track: 4, list: 3, friends: 4, results: 4, 'schedule-rows': 3, card: 1, lines: 2};
const total = () => props.count || defaults[props.variant] || 3;
const widths = [86, 64, 78, 52, 70, 58];
const width = n => widths[(n - 1) % widths.length] + '%';
const range = n => Array.from({length: n}, (_, index) => index + 1);
</script>

<template>
  <div class="skeleton" :class="'skeleton-' + variant" role="status" aria-live="polite" aria-busy="true">
    <span class="sr-only">{{ label }}</span>
    <div aria-hidden="true" class="sk-root">
      <!-- Your Decks -->
      <template v-if="variant === 'decks'">
        <div class="page-heading"><div><span class="sk sk-h1" style="width:min(210px,56%)"></span></div><span class="sk sk-line sk-xs"></span></div>
        <div class="deck-tools"><div class="new-deck-form"><div><span class="sk sk-label"></span><span class="sk sk-input"></span></div><span class="sk sk-btn"></span></div><span class="sk sk-btn sk-btn-wide"></span></div>
        <div class="collection-tools"><span class="sk sk-select"></span><span class="sk sk-line sk-xs"></span></div>
        <div class="deck-grid"><SkeletonTile v-for="n in 6" :key="n"/></div>
      </template>

      <!-- Deck workspace -->
      <template v-else-if="variant === 'deck'">
        <div class="breadcrumbs"><span class="sk sk-line sk-xs"></span></div>
        <div class="page-heading"><div><span class="sk sk-eyebrow"></span><span class="sk sk-h1" style="width:min(300px,70%)"></span><span class="sk sk-line sk-xs"></span></div>
          <div class="actions"><span class="sk sk-btn sk-btn-wide"></span><span class="sk sk-btn sk-btn-icon"></span></div></div>
        <section class="visibility-controls panel"><span class="sk sk-line sk-xs"></span><span class="sk sk-select"></span><span class="sk sk-btn sk-btn-small sk-btn-wide"></span><span class="sk sk-btn sk-btn-small sk-btn-wide"></span></section>
        <section class="card-composer panel">
          <div class="composer-heading"><span class="sk sk-line sk-h2" style="width:130px"></span><span class="sk sk-btn sk-btn-small sk-btn-wide"></span></div>
          <div class="editor-sides"><div class="sk-editor-side"><span class="sk sk-label"></span><span class="sk sk-textarea"></span></div><div class="sk-editor-side"><span class="sk sk-label"></span><span class="sk sk-textarea"></span></div></div>
          <div class="composer-actions"><span class="sk sk-line sk-xs"></span><div class="actions"><span class="sk sk-btn sk-btn-wide"></span></div></div>
        </section>
        <div class="section-heading"><span class="sk sk-line sk-h2" style="width:120px"></span><span class="sk sk-select"></span></div>
        <span class="sk sk-input sk-search"></span>
        <div class="card-list">
          <article v-for="n in 3" :key="n" class="saved-card">
            <div class="saved-card-heading"><span class="sk sk-badge"></span><div class="actions"><span class="sk sk-btn sk-btn-small sk-btn-icon"></span><span class="sk sk-btn sk-btn-small sk-btn-icon"></span></div></div>
            <div class="saved-card-sides"><div v-for="side in 2" :key="side" class="saved-side"><span class="sk sk-label"></span><span class="sk sk-line sk-text" :style="{width: width(n + side)}"></span><span class="sk sk-line sk-text" :style="{width: width(n + side + 2)}"></span></div></div>
          </article>
        </div>
      </template>

      <!-- Shared / public deck -->
      <template v-else-if="variant === 'shared-deck'">
        <div class="deck-workspace">
          <div class="page-heading"><div><span class="sk sk-badge"></span><span class="sk sk-h1" style="width:min(300px,70%)"></span><span class="sk sk-line sk-xs"></span></div>
            <div class="actions"><span class="sk sk-btn sk-btn-wide"></span><span class="sk sk-btn sk-btn-wide"></span></div></div>
          <div class="card-list">
            <article v-for="n in 3" :key="n" class="saved-card"><span class="sk sk-label"></span><span class="sk sk-line sk-text" :style="{width: width(n)}"></span><span class="sk sk-line sk-text" :style="{width: width(n + 3)}"></span><span class="sk sk-line sk-summary"></span></article>
          </div>
        </div>
      </template>

      <!-- Home -->
      <div v-else-if="variant === 'home'" class="home-dashboard">
        <div class="home-main">
          <span class="sk sk-h1 sk-greeting"></span>
          <section class="panel schedule-card">
            <div class="schedule-header"><span class="sk sk-avatar sk-avatar-lg"></span><div class="schedule-title"><span class="sk sk-line sk-h2" style="width:150px"></span><span class="sk sk-line sk-xs" style="width:200px"></span></div><span class="sk sk-btn sk-btn-small sk-btn-wide"></span></div>
            <div class="schedule-days"><span v-for="n in 7" :key="n" class="sk sk-day"></span></div>
            <div class="sk-rows sk-schedule-rows"><div v-for="n in 3" :key="n" class="sk-schedule-row"><span class="sk sk-line sk-time"></span><div class="sk-stack"><span class="sk sk-line sk-strong" :style="{width: width(n)}"></span><span class="sk sk-line sk-small" style="width:36%"></span></div></div></div>
          </section>
          <section class="recent-section explore-section">
            <div class="section-heading explore-heading"><span class="sk sk-line sk-h2" style="width:190px"></span><span class="sk sk-input sk-explore"></span><div class="carousel-controls"><span class="sk sk-btn sk-btn-icon"></span><span class="sk sk-btn sk-btn-icon"></span></div></div>
            <div class="recent-track sk-track"><SkeletonTile v-for="n in 4" :key="n" :buttons="2"/></div>
          </section>
        </div>
        <aside class="home-widgets">
          <section class="panel streak-panel"><div class="section-heading"><span class="sk sk-line sk-h2" style="width:110px"></span></div><span class="sk sk-line sk-streak"></span><span class="sk sk-line sk-text" style="width:90%"></span>
            <div class="study-week"><span v-for="n in 7" :key="n" class="sk sk-weekday"></span></div></section>
          <section class="panel friends-panel home-friends"><div class="section-heading"><span class="sk sk-line sk-h2" style="width:80px"></span><span class="sk sk-btn sk-btn-small sk-btn-wide"></span></div>
            <div class="sk-rows"><div v-for="n in 3" :key="n" class="sk-row-plain"><span class="sk sk-avatar"></span><div class="sk-stack"><span class="sk sk-line sk-strong" :style="{width: width(n)}"></span><span class="sk sk-line sk-small" style="width:34%"></span></div></div></div></section>
        </aside>
      </div>

      <!-- Profile -->
      <template v-else-if="variant === 'profile'">
        <section class="panel profile-card profile-header">
          <span class="sk sk-avatar sk-avatar-profile"></span>
          <div class="profile-identity"><span class="sk sk-h1" style="width:min(260px,80%)"></span><span class="sk sk-line sk-strong" style="width:140px"></span><span class="sk sk-line sk-small" style="width:110px"></span></div>
          <div class="profile-actions"><span class="sk sk-btn"></span><span class="sk sk-btn"></span></div>
        </section>
        <div class="profile-layout">
          <aside class="profile-sidebar"><section class="panel"><span class="sk sk-line sk-h2" style="width:90px"></span><span class="sk sk-line sk-text" style="width:92%"></span><span class="sk sk-line sk-text" style="width:76%"></span><span class="sk sk-line sk-text" style="width:58%"></span></section></aside>
          <div class="profile-main"><section class="profile-public">
            <div class="section-heading"><span class="sk sk-line sk-h2" style="width:150px"></span></div>
            <div class="profile-filters"><span class="sk sk-input"></span><span class="sk sk-select sk-select-wide"></span></div>
            <div class="deck-grid profile-deck-grid"><SkeletonTile v-for="n in 3" :key="n" :buttons="2"/></div>
          </section></div>
        </div>
      </template>

      <!-- Study summary -->
      <div v-else-if="variant === 'summary'" class="study-shell">
        <div class="summary-heading"><span class="sk sk-check"></span><span class="sk sk-eyebrow sk-center"></span><span class="sk sk-h1 sk-center" style="width:min(380px,80%)"></span><span class="sk sk-line sk-text sk-center" style="width:min(520px,90%)"></span></div>
        <div class="summary-grid"><div v-for="n in 3" :key="n" class="stat"><span class="sk sk-line sk-small sk-center" style="width:60%"></span><span class="sk sk-line sk-value sk-center"></span></div></div>
        <div class="actions summary-actions"><span class="sk sk-btn sk-btn-wide"></span><span class="sk sk-btn sk-btn-wide"></span></div>
      </div>

      <!-- Study card: progress, flashcard sheet and rating buttons -->
      <template v-else-if="variant === 'study-card'">
        <div class="progress-text"><span class="sk sk-line sk-xs"></span><span class="sk sk-line sk-xs"></span></div>
        <span class="sk sk-progress"></span>
        <article class="study-sheet sk-sheet">
          <section class="study-question"><span class="sk sk-label"></span><span class="sk sk-line sk-text" style="width:70%"></span><span class="sk sk-line sk-text" style="width:48%"></span></section>
          <div class="study-reveal-prompt"><span class="sk sk-btn sk-btn-wide sk-center-block"></span></div>
        </article>
        <div class="study-actions"><span class="sk sk-line sk-text sk-center" style="width:min(340px,80%)"></span>
          <div class="ratings recall-ratings"><span v-for="n in 3" :key="n" class="sk sk-rating"></span></div></div>
      </template>

      <!-- Class Schedule timetable -->
      <template v-else-if="variant === 'schedule'">
        <div class="section-heading schedule-timetable-heading"><span class="sk sk-line sk-h2" style="width:170px"></span><span class="sk sk-btn sk-btn-small sk-btn-wide"></span></div>
        <div class="timetable"><section v-for="n in 7" :key="n" class="tt-day"><span class="sk sk-line sk-strong" style="width:55%"></span>
          <span v-if="n % 2" class="sk sk-tt-card"></span><span v-if="n % 3 === 1" class="sk sk-tt-card"></span><span class="sk sk-btn sk-btn-small sk-tt-add"></span></section></div>
      </template>

      <!-- Deck tiles: Public Decks on a profile -->
      <div v-else-if="variant === 'grid'" class="deck-grid"><SkeletonTile v-for="n in total()" :key="n"/></div>
      <!-- Deck tiles: the horizontal Explore row on Home -->
      <div v-else-if="variant === 'track'" class="recent-track sk-track"><SkeletonTile v-for="n in total()" :key="n"/></div>

      <!-- Friends and recent visits: avatar with a name and a status line -->
      <div v-else-if="variant === 'list' || variant === 'friends'" class="sk-rows" :class="{'sk-rows-large': variant === 'friends'}">
        <div v-for="n in total()" :key="n" class="sk-row-plain"><span class="sk sk-avatar"></span><div class="sk-stack"><span class="sk sk-line sk-strong" :style="{width: width(n)}"></span><span class="sk sk-line sk-small" :style="{width: (28 + (n % 3) * 8) + '%'}"></span></div></div>
      </div>

      <!-- Search results -->
      <ul v-else-if="variant === 'results'" class="search-list sk-results">
        <li v-for="n in total()" :key="n" class="search-result"><span class="sk sk-avatar sk-avatar-result"></span><div class="sk-stack"><span class="sk sk-line sk-strong" :style="{width: width(n)}"></span><span class="sk sk-line sk-small" :style="{width: (34 + (n % 3) * 10) + '%'}"></span></div></li>
      </ul>

      <!-- Class rows on Home -->
      <div v-else-if="variant === 'schedule-rows'" class="sk-rows sk-schedule-rows"><div v-for="n in total()" :key="n" class="sk-schedule-row"><span class="sk sk-line sk-time"></span><div class="sk-stack"><span class="sk sk-line sk-strong" :style="{width: width(n)}"></span><span class="sk sk-line sk-small" style="width:36%"></span></div></div></div>

      <!-- A single study card (multiple choice, shared study, rooms) -->
      <div v-else-if="variant === 'card'" class="sk sk-card"><span class="sk sk-line sk-center" style="width:55%"></span><span class="sk sk-line sk-center" style="width:35%"></span></div>

      <template v-else-if="variant === 'page'">
        <span class="sk sk-h1" style="width:min(260px,60%)"></span>
        <div class="sk sk-panel"><span v-for="n in total()" :key="n" class="sk sk-line" :style="{width: (92 - n * 14) + '%'}"></span></div>
        <div class="sk-grid"><span v-for="n in 3" :key="n" class="sk sk-tile"></span></div>
      </template>

      <div v-else class="sk-lines"><span v-for="n in range(total())" :key="n" class="sk sk-line" :style="{width: (85 - n * 20) + '%'}"></span></div>
    </div>
  </div>
</template>
