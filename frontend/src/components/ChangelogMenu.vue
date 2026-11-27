<script setup>
import {computed, nextTick, ref} from 'vue';
import releases from '../data/changelog.json';
import {useEvent} from '../composables/lifecycle.js';
import {useNow} from '../composables/clock.js';
import {latestReleases} from '../services/changelog.js';

const root = ref(), panel = ref();
const open = ref(false), expanded = ref(null);
const now = useNow();
const items = computed(() => latestReleases(releases, now.value));
const full = value => new Date(value).toLocaleString(undefined, {dateStyle:'long', timeStyle:'short'});

async function toggle() {
  open.value = !open.value;
  expanded.value = null;
  if (open.value) { await nextTick(); panel.value?.querySelector('button')?.focus(); }
}
function close(restoreFocus = false) {
  if (!open.value) return;
  open.value = false;
  if (restoreFocus) root.value?.querySelector('.changelog-trigger')?.focus();
}
function move(event, step) {
  const entries = [...panel.value.querySelectorAll('.changelog-entry')];
  const index = entries.indexOf(document.activeElement);
  event.preventDefault();
  entries[(index + step + entries.length) % entries.length]?.focus();
}
useEvent(document, 'click', event => { if (!root.value?.contains(event.target)) close(); });
useEvent(document, 'keydown', event => { if (event.key === 'Escape' && open.value) close(true); });
</script>

<template>
  <div ref="root" class="changelog-menu">
    <button id="open-changelog" type="button" class="topbar-icon secondary flat-button changelog-trigger" aria-label="What’s new" aria-haspopup="dialog" aria-controls="changelog-panel" :aria-expanded="open" @click="toggle">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m12 3 1.9 5.1L19 10l-5.1 1.9L12 17l-1.9-5.1L5 10l5.1-1.9zM19 16l.7 1.8L21.5 18.5l-1.8.7L19 21l-.7-1.8-1.8-.7 1.8-.7z"/></svg>
    </button>
    <section v-show="open" id="changelog-panel" ref="panel" class="changelog-panel" role="dialog" aria-label="What’s New" @keydown.down="move($event, 1)" @keydown.up="move($event, -1)">
      <h2>What’s New</h2>
      <ol v-if="items.length" class="changelog-list">
        <li v-for="item in items" :key="item.id">
          <button type="button" class="changelog-entry" :aria-expanded="expanded === item.id" @click="expanded = expanded === item.id ? null : item.id">
            <span class="changelog-top"><strong>{{ item.title }}</strong><time :datetime="item.date" :title="full(item.date)">{{ item.when }}</time></span>
            <span class="changelog-summary" :class="{full:expanded === item.id}">{{ item.summary }}</span>
          </button>
        </li>
      </ol>
      <p v-else class="muted changelog-empty">No updates yet.</p>
    </section>
  </div>
</template>
