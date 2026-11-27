<script setup>
import {computed, ref} from 'vue';
import {useNow} from '../composables/clock.js';
import {useLifetime} from '../composables/lifecycle.js';
import {account} from '../services/session.js';
import {avatarUrl} from '../services/profiles.js';
import {loadSchedule, schedule, timeFormat} from '../services/schedule-store.js';
import {SCHEDULE_DAYS, WEEKDAYS, dayEntries, formatTime, nextClassMessage, roomOf, scheduleStatus, statusMessage, weekdayIndex} from '../services/schedule.js';
import LoadingSkeleton from './LoadingSkeleton.vue';

// Compact, live view of the saved schedule. Editing lives on /class-schedule.
const {active} = useLifetime();
const now = useNow();
const picked = ref(null), loadError = ref('');
const today = computed(() => weekdayIndex(now.value));
const day = computed(() => picked.value ?? SCHEDULE_DAYS[today.value]?.key ?? SCHEDULE_DAYS[0].key);
const subjects = computed(() => schedule.value?.subjects ?? []);
const nextClass = computed(() => nextClassMessage(subjects.value, timeFormat.value, now.value));
const entries = computed(() => dayEntries(subjects.value, day.value));
// Live indicators apply only while the selected day is today.
const state = computed(() => scheduleStatus(entries.value, day.value, now.value));
const message = computed(() => statusMessage(state.value, day.value, now.value));

async function refresh() {
  loadError.value = '';
  try { await loadSchedule(); }
  catch (error) { if (active() && !schedule.value) loadError.value = error.message; }
}
void refresh();
</script>

<template>
  <section class="panel schedule-card" aria-labelledby="schedule-heading">
    <div class="schedule-header">
      <img class="schedule-avatar" :src="avatarUrl(account?.avatar)" alt="" width="56" height="56">
      <div class="schedule-title"><h2 id="schedule-heading">Class Schedule</h2>
        <p v-if="nextClass" class="muted" role="status">{{ nextClass }}</p></div>
      <a class="button secondary small flat-button schedule-edit" href="/class-schedule">Edit / View Full Schedule</a>
    </div>

    <div class="schedule-days" role="group" aria-label="Schedule day">
      <button v-for="item in SCHEDULE_DAYS" :key="item.key" type="button" :aria-pressed="day === item.key" :aria-label="item.long + (item.key === today ? ' (today)' : '')"
        :class="{today:item.key === today}" @click="picked = item.key">{{ item.short }}</button>
    </div>

    <LoadingSkeleton v-if="!schedule && !loadError" variant="list" :count="3" label="Loading your schedule…"/>
    <p v-else-if="!schedule" class="muted" role="alert">Couldn’t load your schedule. <button type="button" class="link-button" @click="refresh">Try again</button></p>
    <template v-else>
      <p class="schedule-status" role="status" aria-live="polite">{{ message }}</p>
      <ol v-if="entries.length" class="schedule-list" :aria-label="WEEKDAYS[day].long + ' classes'">
        <li v-for="entry in entries" :key="entry.id" :class="['tone-' + entry.subject.color, 'state-' + (state.byId[entry.id] || 'plain')]"
          :aria-current="state.byId[entry.id] === 'ongoing' ? 'true' : undefined">
          <span class="schedule-time">{{ formatTime(entry.start, timeFormat) }}<small>{{ formatTime(entry.end, timeFormat) }}</small></span>
          <span class="schedule-subject"><strong>{{ entry.subject.name }}</strong><small v-if="roomOf(entry.subject, entry.meeting)">{{ roomOf(entry.subject, entry.meeting) }}</small></span>
          <span v-if="state.byId[entry.id] === 'ongoing'" class="schedule-flag now">Now</span>
          <span v-else-if="state.byId[entry.id] === 'next'" class="schedule-flag next">Up Next</span>
          <span v-else-if="state.byId[entry.id] === 'done'" class="sr-only">Finished</span>
        </li>
      </ol>
      <p v-if="!subjects.length" class="schedule-cta">Add your classes to see them here. <a href="/class-schedule">Add your first class</a></p>
    </template>
  </section>
</template>
