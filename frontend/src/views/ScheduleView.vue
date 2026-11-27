<script setup>
import {computed, ref} from 'vue';
import {icon} from '../../js/icons.js';
import {useNow} from '../composables/clock.js';
import {useLifetime} from '../composables/lifecycle.js';
import {showNotice} from '../services/notice.js';
import {deleteSubject, loadSchedule, schedule, setTimeFormat, timeFormat} from '../services/schedule-store.js';
import {SCHEDULE_DAYS, WEEKDAYS, dayEntries, describeConflict, formatRange, formatTime, roomOf, weekdayIndex} from '../services/schedule.js';
import {buttonFeedback as vButtonFeedback} from '../components/ButtonFeedback.js';
import LoadingSkeleton from '../components/LoadingSkeleton.vue';
import ScheduleActions from '../components/ScheduleActions.vue';
import ScheduleSubjectDialog from '../components/ScheduleSubjectDialog.vue';
import SegmentedSwitch from '../components/SegmentedSwitch.vue';

const FORMATS = [{value:'12h', label:'12H'}, {value:'24h', label:'24H'}];
const {active} = useLifetime();
const now = useNow();
const today = computed(() => weekdayIndex(now.value));
const editor = ref(), confirmDialog = ref();
const loadError = ref(''), toDelete = ref(null), deleting = ref(false);

async function refresh() {
  loadError.value = '';
  try { await loadSchedule(); }
  catch (error) { if (active() && !schedule.value) loadError.value = error.message; }
}
void refresh();

const subjects = computed(() => schedule.value?.subjects ?? []);
const days = computed(() => SCHEDULE_DAYS.map(day => ({...day, entries:dayEntries(subjects.value, day.key)})));
const overlapping = computed(() => new Set((schedule.value?.conflicts ?? []).flatMap(item => [item.a.meeting_id, item.b.meeting_id])));
const conflictCount = computed(() => schedule.value?.conflicts.length ?? 0);

// Keep existing Sunday-only subjects editable without giving Sunday a timetable column.
const outsideTimetable = computed(() => subjects.value.filter(subject => subject.meetings.every(meeting => meeting.weekday === 6)));
const edit = subject => editor.value.open(subject);
function askDelete(subjectOrId) {
  toDelete.value = typeof subjectOrId === 'object' ? subjectOrId : subjects.value.find(item => item.id === subjectOrId) ?? null;
  if (toDelete.value) confirmDialog.value.showModal();
}
async function confirmDelete() {
  if (deleting.value || !toDelete.value) return;
  deleting.value = true;
  try {
    await deleteSubject(toDelete.value.id);
    if (active()) { showNotice('Class deleted.', true); confirmDialog.value.close(); }
  } catch (error) { if (active()) showNotice(error.message); }
  finally { if (active()) deleting.value = false; }
}
const changeFormat = format => setTimeFormat(format).catch(error => showNotice(error.message));
const entryLabel = entry => `Edit ${entry.subject.name}, ${WEEKDAYS[entry.meeting.weekday].long} ${formatRange(entry.start, entry.end, timeFormat.value)}`;
</script>

<template>
  <div class="schedule-page">
    <div class="page-heading">
      <h1>Class Schedule</h1>
      <div class="actions schedule-actions">
        <SegmentedSwitch :model-value="timeFormat" :options="FORMATS" label="Time format" :disabled="!schedule" @update:model-value="changeFormat"/>
      </div>
    </div>

    <LoadingSkeleton v-if="!schedule && !loadError" variant="page" label="Loading your schedule…"/>
    <section v-else-if="!schedule" class="panel" role="alert"><p>{{ loadError }}</p><button type="button" class="secondary flat-button" @click="refresh">Retry</button></section>

    <template v-else>
      <section v-if="conflictCount" class="schedule-warning schedule-conflict-banner" role="status" aria-live="polite">
        <strong>{{ conflictCount }} overlapping meeting time{{ conflictCount === 1 ? '' : 's' }}</strong>
        <ul><li v-for="item in schedule.conflicts.slice(0, 4)" :key="item.a.meeting_id + '-' + item.b.meeting_id">{{ describeConflict(item, timeFormat) }}</li></ul>
        <p v-if="conflictCount > 4">…and {{ conflictCount - 4 }} more. Open a class to adjust its times.</p>
      </section>

      <section aria-labelledby="timetable-heading">
        <div class="section-heading schedule-timetable-heading">
          <h2 id="timetable-heading">Weekly timetable</h2>
          <ScheduleActions :has-classes="subjects.length > 0" :format="timeFormat"/>
        </div>
        <div class="timetable">
          <section v-for="day in days" :key="day.key" class="tt-day" :class="{today:day.key === today}" :aria-labelledby="'tt-day-' + day.key">
            <h3 :id="'tt-day-' + day.key">{{ day.long }}<span v-if="day.key === today" class="badge tt-today">Today</span></h3>
            <ul v-if="day.entries.length" class="tt-list">
              <li v-for="entry in day.entries" :key="entry.id">
                <button type="button" class="tt-card" :class="['tone-' + entry.subject.color, {overlap:overlapping.has(entry.id)}]" :aria-label="entryLabel(entry)" @click="edit(entry.subject)">
                  <span class="tt-time"><span>{{ formatTime(entry.start, timeFormat) }}</span> <span>– {{ formatTime(entry.end, timeFormat) }}</span></span>
                  <strong>{{ entry.subject.name }}</strong>
                  <small v-if="roomOf(entry.subject, entry.meeting)">{{ roomOf(entry.subject, entry.meeting) }}</small>
                  <span v-if="overlapping.has(entry.id)" class="tt-overlap">Overlap</span>
                </button>
              </li>
            </ul>
            <button type="button" class="secondary flat-button tt-add" :aria-label="'Add class on ' + day.long"
              @click="editor.open(null, day.key)"><span aria-hidden="true" v-html="icon('plus')"></span> Add Class</button>
          </section>
        </div>
      </section>

      <section v-if="outsideTimetable.length" aria-label="Other saved classes" class="subjects-section">
        <ul class="subject-list">
          <li v-for="subject in outsideTimetable" :key="subject.id" class="subject-card" :class="'tone-' + subject.color">
            <div class="subject-card-main">
              <h3>{{ subject.name }}<small v-if="subject.code" class="subject-code">{{ subject.code }}</small></h3>
              <p v-if="subject.instructor" class="muted">{{ subject.instructor }}</p>
            </div>
            <div class="actions subject-card-actions">
              <button type="button" class="secondary small flat-button" :aria-label="'Edit ' + subject.name" @click="edit(subject)">Edit</button>
              <button type="button" class="danger small flat-button" :aria-label="'Delete ' + subject.name" @click="askDelete(subject)">Delete</button>
            </div>
          </li>
        </ul>
      </section>
    </template>

    <ScheduleSubjectDialog ref="editor" @delete="askDelete"/>
    <Teleport to="body">
      <dialog ref="confirmDialog" v-button-feedback class="profile-dialog schedule-confirm" aria-labelledby="delete-class-title" @cancel.prevent="!deleting && confirmDialog.close()">
        <div class="dialog-heading"><h2 id="delete-class-title">Delete class?</h2></div>
        <p>“{{ toDelete?.name }}” and all of its meeting times will be removed from your schedule. This can’t be undone.</p>
        <div class="actions">
          <button type="button" class="secondary flat-button" :disabled="deleting" @click="confirmDialog.close()">Cancel</button>
          <button type="button" class="danger flat-button" :disabled="deleting" @click="confirmDelete">{{ deleting ? 'Deleting…' : 'Delete class' }}</button>
        </div>
      </dialog>
    </Teleport>
  </div>
</template>
