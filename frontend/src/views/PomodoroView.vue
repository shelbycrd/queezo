<script setup>
import {computed, reactive, ref, watch} from 'vue';
import {showNotice} from '../services/notice.js';
import {useLifetime} from '../composables/lifecycle.js';
import {dismissTimerAlert, permissionStatus, storageAvailable, timerState as state, timerText, timeRemaining, transact} from '../services/pomodoro.js';
import {playTimerPress} from '../../js/audio.js';
import {addTask, currentTask, nextTask, pauseTimer, PHASE_NAMES,
  removeTask, resetTimer, setSettings, skipPhase, startTimer} from '../../js/pomodoro-core.js';

const {active} = useLifetime();
const settings = reactive({...state.value.settings});
const permission = ref(permissionStatus());
const title = ref(''), target = ref(2), titleField = ref(), adding = ref(false);
const selectedTask = computed(() => state.value.phase === 'study' ? currentTask(state.value) : nextTask(state.value));
const taskLabel = computed(() => state.value.awaitingStart || state.value.phase !== 'study' || (state.value.running && !state.value.assignedTaskId) ? 'Up next' : 'Current task');
const actionLabel = computed(() => state.value.running ? 'Pause' : state.value.awaitingStart
  ? 'Start ' + PHASE_NAMES[state.value.phase].toLowerCase() : state.value.remainingMs < state.value.intervalMs ? 'Resume' : 'Start');
const notificationText = {
  granted:'Desktop notifications are enabled. Queezo also shows an alert at every timer change.',
  denied:'Desktop notifications are blocked in your browser. In-app alerts will still appear.',
  unavailable:'Desktop notifications are unavailable in this browser. In-app alerts will still appear.',
  default:'In-app alerts are on. Enable desktop notifications to receive timer and task updates outside the page.',
};
const storageMessage = 'Browser storage is unavailable. Your timer and tasks will last only while this page stays open.';
watch(storageAvailable, available => { if (!available) showNotice(storageMessage); }, {immediate:true});
async function act(action, options) {
  try { await transact(action,options); } catch (error) { if (active()) showNotice(error.message); }
}
function toggle() {
  void playTimerPress();
  void act(value => value.running ? pauseTimer(value) : startTimer(value), {skipOnCompletion:true});
}
function skip() {
  void act(value => { skipPhase(value); dismissTimerAlert(); }, {skipOnCompletion:true});
}
async function saveTimers() {
  try {
    await transact(value => setSettings(value, {...settings}));
    if (active()) showNotice('Timers saved. Reset to apply to this interval now.', true);
  } catch (error) { if (active()) showNotice(error.message); }
}
async function queueTask() {
  if (adding.value) return;
  adding.value = true;
  const item = {id:crypto.randomUUID(), title:title.value, target:Number(target.value)};
  try { await act(value => { addTask(value,item); title.value = ''; }); }
  finally { adding.value = false; }
}
async function enableAlerts() {
  try {
    permission.value = await Notification.requestPermission();
    if (permission.value === 'granted' && 'serviceWorker' in navigator) await navigator.serviceWorker.register('/pomodoro-worker.js');
  } catch { if (active()) showNotice('Desktop alerts could not be enabled. In-app alerts remain on.'); }
}
</script>
<template>
  <div class="page-heading"><div><h1>Pomodoro</h1></div></div>
  <div class="pomodoro-layout pomodoro-focus-layout"><div class="pomodoro-main">
    <section class="panel timer-panel pomodoro-focus-timer" aria-label="Pomodoro timer">
      <div class="pomodoro-modes" aria-label="Timer intervals"><span v-for="(name, phase) in PHASE_NAMES" :key="phase" class="pomodoro-mode" :class="{active:phase === state.phase}" :data-pomodoro-mode="phase" :aria-current="phase === state.phase ? 'true' : undefined">{{ name }}</span></div>
      <span id="pomodoro-phase" class="sr-only">{{ PHASE_NAMES[state.phase] }}</span>
      <div id="pomodoro-time" class="pomodoro-time" role="timer" aria-label="Time remaining" aria-live="off">{{ timerText }}</div>
      <progress id="pomodoro-progress" aria-label="Current timer progress" :max="state.intervalMs" :value="Math.max(0,state.intervalMs - timeRemaining)"></progress>
      <p id="pomodoro-current" class="pomodoro-current">{{ selectedTask ? taskLabel + ': ' + selectedTask.title : 'Free study · add a task whenever you need one' }}</p>
      <div class="timer-actions"><button id="pomodoro-reset" type="button" class="secondary flat-button" @click="act(resetTimer)">Reset timer</button><button id="pomodoro-toggle" type="button" :aria-label="actionLabel" :title="actionLabel" @click="toggle">
        <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><template v-if="state.running"><rect x="6" y="4" width="4" height="16" rx="1"/><rect x="14" y="4" width="4" height="16" rx="1"/></template><path v-else d="M7 4.7a1 1 0 0 1 1.5-.86l12 7.3a1 1 0 0 1 0 1.72l-12 7.3A1 1 0 0 1 7 19.3z"/></svg>
      </button><button id="pomodoro-skip" type="button" class="secondary flat-button" title="Skip to the next phase" @click="skip">Skip</button></div>
      <div class="cycle-info"><span id="pomodoro-cycle">{{ state.completedInCycle }} of 4 study sessions complete</span><span id="pomodoro-total" class="muted">{{ state.totalPomodoros }} total</span></div>
      <div id="pomodoro-dots" class="pomodoro-dots" aria-label="Study sessions completed this cycle"><span v-for="n of 4" :key="n" class="pomodoro-dot" :class="{complete:n <= state.completedInCycle}">{{ n }}</span></div>
      <p class="hint">Four study sessions, then a long break. Start each next phase when you’re ready.</p>
    </section>
    <details class="panel pomodoro-settings"><summary>Timer settings <span class="muted">minutes</span></summary><form id="pomodoro-settings-form" @submit.prevent="saveTimers"><div class="timer-settings-inputs">
      <div v-for="(label,phase) in {study:'Study timer',short:'Short break',long:'Long break'}" :key="phase"><label :for="phase + '-minutes'">{{ label }}</label><input :id="phase + '-minutes'" :name="phase" v-model="settings[phase]" type="number" min="0.01" max="180" step="0.01" required></div></div>
      <p class="hint">New durations apply to the next interval. Reset applies them to the current timer. You can use decimals for small timers.</p><button type="submit" class="secondary small">Save timers</button><p id="timer-settings-message" class="hint" role="status"></p>
    </form></details>
    <section class="panel notification-panel"><h2>Timer alerts</h2><p id="notification-status" class="muted">{{ notificationText[permission] }}</p><button v-if="permission === 'default'" id="enable-pomodoro-notifications" class="secondary small" type="button" @click="enableAlerts">Enable desktop notifications</button><p class="hint">Keep Queezo open. Your settings and tasks stay saved in this browser.</p></section>
  </div><section class="panel pomodoro-tasks"><div class="section-heading course-heading"><h2>Tasks</h2><span id="pomodoro-task-count" class="muted">{{ state.tasks.filter(item => item.completed < item.target).length }} remaining</span></div>
    <p class="hint">Set your pomodoros. We'll take care of moving to the next task.</p>
    <form id="pomodoro-task-form" @submit.prevent="queueTask"><label for="pomodoro-task-title">Task</label><input id="pomodoro-task-title" v-model="title" ref="titleField" name="title" maxlength="160" required placeholder="e.g. Do assignment">
      <div class="task-estimates" aria-label="Quick pomodoro estimate"><button v-for="n in [1,2,4]" :key="n" type="button" class="secondary small flat-button" :aria-pressed="target === n" @click="target = n; titleField.focus()">{{ n }} {{ n === 1 ? 'pomodoro' : 'pomodoros' }}</button></div>
      <div class="task-add-row"><div><label for="pomodoro-task-target">Pomodoros needed</label><input id="pomodoro-task-target" v-model="target" name="target" type="number" min="1" max="99" step="1" required></div><button type="submit" :disabled="adding">+ Add task</button></div>
    </form>
    <div id="pomodoro-task-list"><ol v-if="state.tasks.length" class="task-queue">
      <li v-for="item in state.tasks" :key="item.id" class="queued-task" :class="{'task-done':item.completed === item.target,'task-active':item.completed < item.target && selectedTask?.id === item.id}">
        <div class="task-heading"><h3>{{ item.title }}</h3><span class="badge">{{ item.completed === item.target ? 'Done' : selectedTask?.id === item.id ? state.phase === 'study' && !state.awaitingStart ? 'Current' : 'Next' : 'Queued' }}</span></div>
        <div class="task-progress-label"><span>{{ item.completed }} / {{ item.target }} pomodoros</span><button type="button" class="remove-course" :disabled="state.assignedTaskId === item.id" :title="state.assignedTaskId === item.id ? 'Reset the study timer to remove this task' : undefined" :aria-label="'Remove task: ' + item.title" @click="act(value => removeTask(value,item.id))">Remove</button></div>
        <progress :max="item.target" :value="item.completed" :aria-label="'Progress for ' + item.title"></progress>
      </li></ol><div v-else class="task-empty"><p>No tasks queued yet.</p><p class="hint">Add a task above or start a free study session.</p></div></div>
  </section></div>
</template>
