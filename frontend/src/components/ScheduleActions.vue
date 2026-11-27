<script setup>
import {computed, nextTick, ref} from 'vue';
import {icon} from '../../js/icons.js';
import {useLifetime} from '../composables/lifecycle.js';
import {showNotice} from '../services/notice.js';
import {clearSchedule, loadScheduleArchive, loadScheduleHistory, restoreSchedule} from '../services/schedule-store.js';
import {WEEKDAYS, dayEntries, formatRange, roomOf} from '../services/schedule.js';

defineProps({hasClasses:Boolean, format:{type:String, required:true}});
const {active, signal} = useLifetime();
const menu = ref(), trigger = ref(), clearDialog = ref(), historyDialog = ref(), historyHeading = ref();
const history = ref(null), selected = ref(null);
const loading = ref(false), pending = ref(false), confirming = ref(false), error = ref('');
let request = 0;

const archiveDate = new Intl.DateTimeFormat(undefined, {dateStyle:'medium', timeStyle:'short'});
const dateLabel = entry => archiveDate.format(new Date(entry.archived_at));
const days = computed(() => WEEKDAYS.map(day => ({...day, entries:dayEntries(selected.value?.subjects ?? [], day.key)}))
  .filter(day => day.entries.length));
const focusHeading = () => void nextTick(() => historyHeading.value?.focus());

function closeMenu() {
  menu.value.open = false;
  trigger.value.focus();
}
function leaveMenu(event) {
  if (!menu.value.contains(event.relatedTarget)) menu.value.open = false;
}
function openClear() {
  closeMenu();
  error.value = '';
  clearDialog.value.showModal();
}
async function confirmClear() {
  if (pending.value) return;
  pending.value = true;
  error.value = '';
  try {
    await clearSchedule();
    if (active()) {
      clearDialog.value.close();
      showNotice('Schedule cleared and saved to history.', true);
    }
  } catch (failure) {
    if (active()) error.value = failure.message;
  } finally {
    if (active()) pending.value = false;
  }
}

function openHistory() {
  closeMenu();
  history.value = null;
  selected.value = null;
  confirming.value = false;
  historyDialog.value.showModal();
  void loadHistory();
}
function currentRead(ticket) {
  return active() && historyDialog.value.open && ticket === request;
}
async function loadHistory() {
  const ticket = ++request;
  loading.value = true;
  error.value = '';
  try {
    const result = await loadScheduleHistory(signal);
    if (currentRead(ticket)) history.value = result;
  } catch (failure) {
    if (currentRead(ticket)) error.value = failure.message;
  } finally {
    if (currentRead(ticket)) loading.value = false;
  }
}
async function openEntry(entry) {
  const ticket = ++request;
  loading.value = true;
  error.value = '';
  try {
    const {subjects} = await loadScheduleArchive(entry.id, signal);
    if (currentRead(ticket)) {
      selected.value = {...entry, subjects};
      focusHeading();
    }
  } catch (failure) {
    if (currentRead(ticket)) error.value = failure.message;
  } finally {
    if (currentRead(ticket)) loading.value = false;
  }
}
function backToHistory() {
  selected.value = null;
  focusHeading();
  void loadHistory();
}
function showRestoreConfirmation(show) {
  confirming.value = show;
  error.value = '';
  focusHeading();
}
async function confirmRestore() {
  if (pending.value) return;
  pending.value = true;
  error.value = '';
  try {
    await restoreSchedule(selected.value.id);
    if (active()) {
      historyDialog.value.close();
      showNotice('Schedule restored.', true);
    }
  } catch (failure) {
    if (active()) error.value = failure.message;
  } finally {
    if (active()) pending.value = false;
  }
}
</script>

<template>
  <details ref="menu" class="schedule-menu" @focusout="leaveMenu" @keydown.esc.stop="closeMenu">
    <summary ref="trigger" aria-label="Schedule options" v-html="icon('menu')"></summary>
    <div class="schedule-menu-options">
      <button type="button" class="secondary flat-button" :disabled="!hasClasses" aria-haspopup="dialog" @click="openClear">Clear Schedule</button>
      <button type="button" class="secondary flat-button" aria-haspopup="dialog" @click="openHistory">View History</button>
    </div>
  </details>

  <Teleport to="body">
    <dialog ref="clearDialog" class="profile-dialog schedule-confirm" aria-labelledby="clear-schedule-title" @cancel="pending && $event.preventDefault()">
      <div class="dialog-heading"><h2 id="clear-schedule-title">Clear schedule?</h2></div>
      <p>All classes and meeting times will be cleared from your timetable. You can still view or restore this schedule from <strong>View History</strong>.</p>
      <p v-if="error" class="inline-error" role="alert">{{ error }}</p>
      <div class="actions schedule-history-actions">
        <button type="button" class="secondary flat-button" :disabled="pending" @click="clearDialog.close()">Cancel</button>
        <button type="button" class="danger flat-button" :disabled="pending" @click="confirmClear">{{ pending ? 'Clearing…' : 'Clear Schedule' }}</button>
      </div>
    </dialog>

    <dialog ref="historyDialog" class="profile-dialog schedule-history" aria-labelledby="schedule-history-title" @cancel="pending && $event.preventDefault()">
      <div class="dialog-heading">
        <h2 id="schedule-history-title" ref="historyHeading" tabindex="-1">{{ confirming ? 'Restore schedule?' : selected ? 'Saved schedule' : 'Schedule history' }}</h2>
        <button type="button" class="secondary small flat-button" :disabled="pending" @click="historyDialog.close()">Close</button>
      </div>

      <template v-if="confirming">
        <p>Restore the schedule saved on {{ dateLabel(selected) }} to your weekly timetable?</p>
        <p v-if="hasClasses">Your current timetable will be saved to history before it is replaced. History keeps the latest {{ history.limit }} schedules.</p>
        <div class="actions schedule-history-actions">
          <button type="button" class="secondary flat-button" :disabled="pending" @click="showRestoreConfirmation(false)">Back</button>
          <button type="button" :disabled="pending" @click="confirmRestore">{{ pending ? 'Restoring…' : 'Restore Schedule' }}</button>
        </div>
      </template>

      <template v-else-if="selected">
        <p><time :datetime="selected.archived_at">{{ dateLabel(selected) }}</time></p>
        <div class="schedule-history-preview">
          <section v-for="day in days" :key="day.key">
            <h3>{{ day.long }}</h3>
            <ul class="tt-list">
              <li v-for="entry in day.entries" :key="entry.id" class="tt-card schedule-history-class" :class="'tone-' + entry.subject.color">
                <span class="tt-time">{{ formatRange(entry.start, entry.end, format) }}</span>
                <strong>{{ entry.subject.name }}<small v-if="entry.subject.code" class="subject-code">{{ entry.subject.code }}</small></strong>
                <small v-if="roomOf(entry.subject, entry.meeting)">{{ roomOf(entry.subject, entry.meeting) }}</small>
                <small v-if="entry.subject.instructor">{{ entry.subject.instructor }}</small>
              </li>
            </ul>
          </section>
        </div>
        <div class="actions schedule-history-actions">
          <button type="button" class="secondary flat-button" @click="backToHistory">Back to History</button>
          <button type="button" @click="showRestoreConfirmation(true)">Restore Schedule</button>
        </div>
      </template>

      <template v-else>
        <p v-if="loading" role="status">Loading saved schedules…</p>
        <p v-else-if="history && !history.entries.length">Schedules you clear will appear here.</p>
        <ul v-if="history?.entries.length" class="schedule-history-list">
          <li v-for="entry in history.entries" :key="entry.id">
            <button type="button" class="secondary flat-button" :disabled="loading" @click="openEntry(entry)">
              <time :datetime="entry.archived_at">{{ dateLabel(entry) }}</time>
              <span>{{ entry.subject_count }} {{ entry.subject_count === 1 ? 'class' : 'classes' }}</span>
            </button>
          </li>
        </ul>
        <button v-if="error && !loading" type="button" class="secondary flat-button" @click="loadHistory">Refresh History</button>
      </template>
      <p v-if="error" class="inline-error" role="alert">{{ error }}</p>
    </dialog>
  </Teleport>
</template>
