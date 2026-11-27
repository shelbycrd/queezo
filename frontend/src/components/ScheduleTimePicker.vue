<script setup>
import {computed, nextTick, ref} from 'vue';
import {clockDialValue, formatTime, from12Hour, to12Hour} from '../services/schedule.js';
import SegmentedSwitch from './SegmentedSwitch.vue';

const props = defineProps({format:{type:String, required:true}, periods:{type:Array, required:true}});
const emit = defineEmits(['apply', 'close']);
const MODES = [{value:'hour', label:'Hour'}, {value:'minute', label:'Minute'}];
const OUTER_RADIUS = 0.80;
const INNER_RADIUS = 0.52;
const dialog = ref();
const title = ref('');
const time = ref(0);
const mode = ref('hour');
const fine = ref(false);
let pointerId = null;

const twelveHour = computed(() => props.format === '12h');
const isMinute = computed(() => mode.value === 'minute');
const hour = computed(() => Math.floor(time.value / 60));
const minute = computed(() => time.value % 60);
const clock = computed(() => to12Hour(time.value));
const value = computed(() => isMinute.value ? minute.value : twelveHour.value ? clock.value.hour : hour.value);
const minimum = computed(() => !isMinute.value && twelveHour.value ? 1 : 0);
const maximum = computed(() => isMinute.value ? 59 : twelveHour.value ? 12 : 23);
const pad = number => String(number).padStart(2, '0');

function position(turn, radius) {
  const angle = turn * 2 * Math.PI;
  return {
    left:`${50 + 50 * radius * Math.sin(angle)}%`,
    top:`${50 - 50 * radius * Math.cos(angle)}%`,
  };
}
function mark(value, turn, radius, label = value) {
  return {value, label, position:position(turn, radius)};
}
const marks = computed(() => {
  if (isMinute.value) {
    return Array.from({length:12}, (_, index) => mark(index * 5, index / 12, OUTER_RADIUS, pad(index * 5)));
  }
  const outer = Array.from({length:12}, (_, index) => mark(index || 12, index / 12, OUTER_RADIUS));
  if (twelveHour.value) return outer;
  const inner = Array.from({length:12}, (_, index) => {
    const hourValue = index ? index + 12 : 0;
    return mark(hourValue, index / 12, INNER_RADIUS, pad(hourValue));
  });
  return [...outer, ...inner];
});
const hand = computed(() => {
  if (isMinute.value) return {turn:minute.value / 60, radius:OUTER_RADIUS};
  const inner = !twelveHour.value && (hour.value === 0 || hour.value > 12);
  return {turn:(hour.value % 12) / 12, radius:inner ? INNER_RADIUS : OUTER_RADIUS};
});

async function open(minutes, label) {
  time.value = minutes;
  title.value = label;
  mode.value = 'hour';
  fine.value = false;
  pointerId = null;
  await nextTick();
  dialog.value?.showModal();
}
defineExpose({open});

function setPeriod(period) {
  time.value = from12Hour(clock.value.hour, minute.value, period);
}
function pick(value) {
  if (isMinute.value) time.value = hour.value * 60 + value;
  else if (twelveHour.value) time.value = from12Hour(value, minute.value, clock.value.period);
  else time.value = value * 60 + minute.value;
}
function pickAt(event) {
  const bounds = event.currentTarget.getBoundingClientRect();
  const radius = bounds.width / 2;
  const x = (event.clientX - bounds.left - radius) / radius;
  const y = (event.clientY - bounds.top - radius) / radius;
  const selected = clockDialValue(x, y, mode.value, props.format, event.ctrlKey || fine.value);
  if (selected !== null) pick(selected);
}
function startDrag(event) {
  if (event.button !== 0 || pointerId !== null) return;
  pointerId = event.pointerId;
  event.currentTarget.setPointerCapture(pointerId);
  event.currentTarget.focus();
  pickAt(event);
}
function moveDrag(event) {
  if (event.pointerId === pointerId) pickAt(event);
}
function endDrag(event) {
  if (event.pointerId === pointerId) pointerId = null;
}
function keydown(event) {
  const step = isMinute.value && !event.ctrlKey && !fine.value ? 5 : 1;
  const count = maximum.value - minimum.value + 1;
  const previous = minimum.value + (value.value - minimum.value - step + count) % count;
  const next = minimum.value + (value.value - minimum.value + step) % count;
  const selected = {
    ArrowLeft:previous, ArrowDown:previous, ArrowRight:next, ArrowUp:next,
    Home:minimum.value, End:maximum.value,
  }[event.key];
  if (selected === undefined) return;
  event.preventDefault();
  pick(selected);
}
function apply() {
  emit('apply', time.value);
  dialog.value.close();
}
</script>

<template>
  <dialog ref="dialog" class="schedule-clock-dialog" aria-labelledby="schedule-clock-title" @close="emit('close')">
    <h3 id="schedule-clock-title">{{ title }}</h3>
    <span class="schedule-clock-time">{{ formatTime(time, format) }}</span>
    <div class="schedule-clock-controls">
      <SegmentedSwitch v-model="mode" :options="MODES" label="Clock hand"/>
      <SegmentedSwitch v-if="twelveHour" :model-value="clock.period" :options="periods" label="AM or PM" @update:model-value="setPeriod"/>
    </div>
    <div class="schedule-clock-dial" role="slider" tabindex="0"
      :aria-label="isMinute ? 'Minute' : 'Hour'" :aria-valuemin="minimum" :aria-valuemax="maximum" :aria-valuenow="value"
      :aria-describedby="isMinute ? 'schedule-clock-hint' : undefined"
      @keydown="keydown" @pointerdown="startDrag" @pointermove="moveDrag" @lostpointercapture="endDrag">
      <div class="schedule-clock-hand" aria-hidden="true" :style="{height:hand.radius * 50 + '%', transform:'rotate(' + hand.turn + 'turn)'}"></div>
      <div class="schedule-clock-knob" aria-hidden="true" :style="position(hand.turn, hand.radius)"></div>
      <span v-for="item in marks" :key="item.value" class="schedule-clock-mark" :class="{selected:item.value === value}"
        aria-hidden="true" :style="item.position">{{ item.label }}</span>
      <div class="schedule-clock-pin" aria-hidden="true"></div>
    </div>
    <div v-if="isMinute" class="schedule-clock-precision">
      <label><input v-model="fine" type="checkbox"> 1-minute steps</label>
      <p id="schedule-clock-hint">Hold Ctrl while dragging for 1-minute steps.</p>
    </div>
    <div class="actions schedule-clock-actions">
      <button type="button" class="secondary flat-button" @click="dialog.close()">Cancel</button>
      <button type="button" @click="apply">Set time</button>
    </div>
  </dialog>
</template>
