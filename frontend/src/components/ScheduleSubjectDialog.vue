<script setup>
import {computed, nextTick, reactive, ref, watch} from 'vue';
import {icon} from '../../js/icons.js';
import {useLifetime} from '../composables/lifecycle.js';
import {showNotice} from '../services/notice.js';
import {saveSubject, schedule, setTimeFormat, timeFormat} from '../services/schedule-store.js';
import {
  CODE_LIMIT, COLORS, MAX_MEETINGS_PER_SUBJECT, NAME_LIMIT, ROOM_LIMIT, SCHEDULE_DAYS, WEEKDAYS, conflictsForDraft, convertDraft,
  describeConflict, describeScheduleError, draftFromMinutes, expandRows, groupMeetings, parseDraft, validateRow,
} from '../services/schedule.js';
import {buttonFeedback as vButtonFeedback} from './ButtonFeedback.js';
import ScheduleTimePicker from './ScheduleTimePicker.vue';
import SegmentedSwitch from './SegmentedSwitch.vue';

const emit = defineEmits(['saved', 'delete']);
const {active} = useLifetime();
const FORMATS = [{value:'12h', label:'12H'}, {value:'24h', label:'24H'}];
const PERIODS = [{value:'AM', label:'AM'}, {value:'PM', label:'PM'}];
const DEFAULT_TIMES = {start:480, end:570};
const TIME_LABELS = {start:'Start time', end:'End time'};
const dialog = ref(), nameField = ref(), clockPicker = ref(), clockField = ref(null);
const editingId = ref(null), attempted = ref(false), pending = ref(false), serverError = ref('');
const form = reactive({name:'', code:'', instructor:'', location:'', color:'blue'});
const rows = ref([]);
let counter = 0;

const makeRow = row => ({
  key:++counter, days:row.days, ids:row.ids, location:row.location,
  start:draftFromMinutes(row.start, timeFormat.value), end:draftFromMinutes(row.end, timeFormat.value),
});
const blankRow = day => makeRow({days:day == null ? [] : [day], ids:{}, ...DEFAULT_TIMES, location:''});

function open(subject = null, day = null) {
  editingId.value = subject?.id ?? null;
  Object.assign(form, {name:subject?.name ?? '', code:subject?.code ?? '', instructor:subject?.instructor ?? '',
    location:subject?.location ?? '', color:subject?.color ?? 'blue'});
  rows.value = subject ? groupMeetings(subject.meetings).map(makeRow) : [blankRow(day)];
  attempted.value = false; serverError.value = ''; pending.value = false;
  dialog.value.showModal();
  void nextTick(() => nameField.value?.focus());
}
defineExpose({open});

// Switching 12H/24H re-expresses every valid entry in the new format without changing its value.
watch(timeFormat, (to, from) => {
  for (const row of rows.value) { row.start = convertDraft(row.start, from, to); row.end = convertDraft(row.end, from, to); }
});
function changeFormat(format) {
  setTimeFormat(format).catch(error => showNotice(error.message));
}

function openClock(row, side, trigger) {
  const format = timeFormat.value;
  const draft = row[side];
  let {minutes} = parseDraft(draft, format);
  if (minutes === undefined) {
    const fallback = draftFromMinutes(DEFAULT_TIMES[side], format);
    minutes = parseDraft({...fallback, period:draft.period}, format).minutes;
  }
  clockField.value = {row, side};
  trigger.focus();
  void clockPicker.value.open(minutes, TIME_LABELS[side]);
}
function applyClockTime(minutes) {
  const {row, side} = clockField.value;
  row[side] = draftFromMinutes(minutes, timeFormat.value);
}

const checks = computed(() => rows.value.map(row => validateRow(row, timeFormat.value)));
const nameError = computed(() => attempted.value && !form.name.trim() ? 'Enter a subject name.' : '');

// Overlaps with the rest of the schedule are only a warning; the class can still be saved.
const conflicts = computed(() => {
  const meetings = [];
  rows.value.forEach((row, index) => {
    const {start, end, valid} = checks.value[index];
    if (!valid) return;
    for (const weekday of row.days) {
      meetings.push({id:row.ids[weekday] ?? -(row.key * 10 + weekday + 1), weekday, start:toApi(start), end:toApi(end), location:row.location});
    }
  });
  const draft = {id:editingId.value ?? 0, name:form.name.trim() || 'This class', location:form.location, meetings};
  return conflictsForDraft(draft, schedule.value?.subjects ?? []).map(item => describeConflict(item, timeFormat.value));
});
const toApi = minutes => String(Math.floor(minutes / 60)).padStart(2, '0') + ':' + String(minutes % 60).padStart(2, '0');

function toggleDay(row, day) {
  row.days = row.days.includes(day) ? row.days.filter(item => item !== day) : [...row.days, day].sort((a, b) => a - b);
}
function addRow() {
  if (rows.value.length < MAX_MEETINGS_PER_SUBJECT) rows.value.push(blankRow());
}
// A new subject needs every selected day to become a meeting, so the cap is on expanded meetings.
const meetingCount = computed(() => rows.value.reduce((total, row) => total + row.days.length, 0));
const tooMany = computed(() => meetingCount.value > MAX_MEETINGS_PER_SUBJECT);

async function submit() {
  attempted.value = true; serverError.value = '';
  if (pending.value) return;
  if (!form.name.trim() || checks.value.some(check => !check.valid) || tooMany.value) {
    void nextTick(() => dialog.value.querySelector('[aria-invalid="true"]')?.focus());
    return;
  }
  pending.value = true;
  try {
    const body = {
      name:form.name.trim(), code:form.code.trim() || null, instructor:form.instructor.trim() || null,
      location:form.location.trim() || null, color:form.color,
      meetings:expandRows(rows.value.map((row, index) => ({...row, start:checks.value[index].start, end:checks.value[index].end}))),
    };
    const {subjectId, warnings} = await saveSubject(editingId.value, body);
    if (!active()) return;
    emit('saved', subjectId);
    showNotice(warnings.length
      ? `Saved. ${warnings.length} overlapping time${warnings.length === 1 ? '' : 's'} found; review your schedule.`
      : editingId.value ? 'Class updated.' : 'Class added.', true);
    dialog.value.close();
  } catch (error) {
    if (active()) serverError.value = describeScheduleError(error.message);
  } finally { if (active()) pending.value = false; }
}
</script>

<template>
  <Teleport to="body">
    <dialog ref="dialog" v-button-feedback class="schedule-dialog" aria-labelledby="schedule-dialog-title" @cancel="pending && $event.preventDefault()">
      <form novalidate @submit.prevent="submit">
        <div class="dialog-heading"><h2 id="schedule-dialog-title">{{ editingId ? 'Edit class' : 'Add class' }}</h2>
          <button type="button" class="secondary small flat-button" aria-label="Close" :disabled="pending" @click="dialog.close()">×</button></div>

        <fieldset class="schedule-fields" :disabled="pending">
          <legend class="sr-only">Class details</legend>
          <div class="schedule-field wide">
            <label for="subject-name">Subject name <span aria-hidden="true">*</span></label>
            <input id="subject-name" ref="nameField" v-model="form.name" :maxlength="NAME_LIMIT" required autocomplete="off"
              :aria-invalid="Boolean(nameError)" :aria-describedby="nameError ? 'subject-name-error' : undefined">
            <p v-if="nameError" id="subject-name-error" class="field-error" role="alert">{{ nameError }}</p>
          </div>
          <div class="schedule-field"><label for="subject-code">Subject code <small>(optional)</small></label>
            <input id="subject-code" v-model="form.code" :maxlength="CODE_LIMIT" autocomplete="off"></div>
          <div class="schedule-field"><label for="subject-instructor">Instructor <small>(optional)</small></label>
            <input id="subject-instructor" v-model="form.instructor" :maxlength="NAME_LIMIT" autocomplete="off"></div>
          <div class="schedule-field wide"><label for="subject-location">Room / location <small>(optional)</small></label>
            <input id="subject-location" v-model="form.location" :maxlength="ROOM_LIMIT" autocomplete="off"></div>
          <fieldset class="color-picker wide">
            <legend>Color</legend>
            <label v-for="color in COLORS" :key="color.key" :class="'swatch tone-' + color.key">
              <input v-model="form.color" type="radio" name="subject-color" :value="color.key"><span class="swatch-dot" aria-hidden="true"></span>
              <span class="sr-only">{{ color.label }}</span></label>
          </fieldset>
        </fieldset>

        <div class="meetings-heading"><h3>Meeting times</h3>
          <SegmentedSwitch :model-value="timeFormat" :options="FORMATS" label="Time format" @update:model-value="changeFormat"/></div>
        <ul class="meeting-rows">
          <li v-for="(row, index) in rows" :key="row.key" class="meeting-row">
            <fieldset :disabled="pending">
              <legend class="sr-only">Meeting {{ index + 1 }}</legend>
              <div class="meeting-row-head"><strong>Meeting {{ index + 1 }}</strong>
                <button type="button" class="secondary small flat-button" :disabled="rows.length === 1" :aria-label="'Remove meeting ' + (index + 1)" @click="rows.splice(index, 1)">Remove</button></div>
              <div class="day-chips" role="group" :aria-label="'Days for meeting ' + (index + 1)">
                <button v-for="day in (Object.hasOwn(row.ids, 6) ? WEEKDAYS : SCHEDULE_DAYS)" :key="day.key" type="button" class="day-chip" :aria-pressed="row.days.includes(day.key)"
                  :aria-label="day.long" @click="toggleDay(row, day.key)">{{ day.short }}</button>
              </div>
              <p v-if="attempted && checks[index].errors.days" class="field-error" role="alert">{{ checks[index].errors.days }}</p>
              <div class="time-pair">
                <div v-for="side in ['start', 'end']" :key="side" class="time-field">
                  <label :for="side + '-' + row.key">{{ side === 'start' ? 'Start Time' : 'End Time' }}</label>
                  <div class="time-control">
                    <input :id="side + '-' + row.key" v-model="row[side].text" inputmode="numeric" maxlength="5" autocomplete="off" placeholder="08:00"
                      :aria-invalid="attempted && Boolean(checks[index].errors[side])"
                      :aria-describedby="attempted && checks[index].errors[side] ? side + '-error-' + row.key : undefined">
                    <SegmentedSwitch v-if="timeFormat === '12h'" v-model="row[side].period" :options="PERIODS"
                      :label="(side === 'start' ? 'Start' : 'End') + ' time AM or PM, meeting ' + (index + 1)"/>
                    <button type="button" class="secondary flat-button time-picker-button" aria-haspopup="dialog"
                      :aria-label="'Pick ' + TIME_LABELS[side].toLowerCase() + ' for meeting ' + (index + 1)"
                      @click="openClock(row, side, $event.currentTarget)" v-html="icon('clock')"></button>
                  </div>
                  <p v-if="attempted && checks[index].errors[side]" :id="side + '-error-' + row.key" class="field-error" role="alert">{{ checks[index].errors[side] }}</p>
                </div>
              </div>
              <div class="schedule-field"><label :for="'room-' + row.key">Room for this meeting <small>(optional, overrides the subject’s room)</small></label>
                <input :id="'room-' + row.key" v-model="row.location" :maxlength="ROOM_LIMIT" autocomplete="off" :placeholder="form.location || 'Same as the subject'"></div>
            </fieldset>
          </li>
        </ul>
        <div class="meeting-add"><button type="button" class="secondary small flat-button" :disabled="pending || rows.length >= MAX_MEETINGS_PER_SUBJECT" @click="addRow">+ Add meeting time</button>
          <small v-if="tooMany" class="field-error" role="alert">A subject can have up to {{ MAX_MEETINGS_PER_SUBJECT }} meetings.</small></div>

        <div class="schedule-warning" role="status" aria-live="polite">
          <template v-if="conflicts.length">
            <strong>These times overlap your schedule. You can still save.</strong>
            <ul><li v-for="line in conflicts.slice(0, 5)" :key="line">{{ line }}</li></ul>
            <p v-if="conflicts.length > 5">…and {{ conflicts.length - 5 }} more.</p>
          </template>
        </div>
        <p v-if="serverError" class="inline-error" role="alert">{{ serverError }}</p>

        <div class="actions schedule-dialog-actions">
          <button v-if="editingId" type="button" class="danger flat-button schedule-delete" :disabled="pending" @click="emit('delete', editingId); dialog.close()">Delete class</button>
          <button type="button" class="secondary flat-button" :disabled="pending" @click="dialog.close()">Cancel</button>
          <button type="submit" :disabled="pending">{{ pending ? 'Saving…' : editingId ? 'Save changes' : 'Add class' }}</button>
        </div>
      </form>
    </dialog>
    <ScheduleTimePicker ref="clockPicker" :format="timeFormat" :periods="PERIODS"
      @apply="applyClockTime" @close="clockField = null"/>
  </Teleport>
</template>
