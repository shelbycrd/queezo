<script setup>
import {computed, nextTick, ref, shallowRef} from 'vue';
import {api} from '../../js/api.js';
import {formatGradeDisplay, normalizeGradeInput} from '../../js/gwa-input.js';
import {showNotice} from '../services/notice.js';
import {useLifetime} from '../composables/lifecycle.js';
import CopyButton from '../components/CopyButton.vue';

let id = 0;
const emptyCourse = () => ({id:++id,subject:'',units:'',grade:''});
const courses = ref([emptyCourse()]);
const summary = shallowRef(null), pending = ref(false), result = ref(), form = ref(), submitButton = ref();
const {active,signal} = useLifetime();
const percentage = computed(() => Math.max(0,Math.min(100,summary.value.percentage)));
const focusSubject = async index => { await nextTick(); form.value?.querySelector('#subject-' + index)?.focus(); };
async function addCourse() {
  if (pending.value || courses.value.length >= 15) return;
  courses.value.push(emptyCourse()); summary.value = null;
  await focusSubject(courses.value.length - 1);
}
async function remove(index) {
  if (pending.value || courses.value.length === 1) return;
  courses.value.splice(index,1); summary.value = null;
  await focusSubject(Math.min(index,courses.value.length - 1));
}
async function clear() {
  courses.value = [emptyCourse()]; summary.value = null;
  await focusSubject(0);
}
function gradeInput(event, course) {
  const input = event.target, original = input.value;
  if (event.isComposing) return;
  course.grade = event.type === 'blur' ? formatGradeDisplay(original) :
    event.inputType?.startsWith('delete') ? original : normalizeGradeInput(original);
  if (course.grade !== original) {
    input.value = course.grade;
    if (event.type !== 'blur') input.setSelectionRange(course.grade.length,course.grade.length);
  }
  const grade = course.grade;
  input.setCustomValidity(!grade || (/^\d+(?:\.\d{0,6})?$/.test(grade) && Number(grade) >= 1 && Number(grade) <= 5)
    ? '' : 'Enter a grade from 1.00 to 5.00.');
  if (event.type !== 'blur') summary.value = null;
}
function enter(event,index) {
  if (event.key !== 'Enter' || !event.target.matches('input') || event.isComposing || event.repeat || pending.value) return;
  event.preventDefault();
  const invalid = [...event.currentTarget.querySelectorAll('input')].find(input => !input.checkValidity());
  if (invalid) { invalid.reportValidity(); invalid.focus(); return; }
  if (index + 1 < courses.value.length) void focusSubject(index + 1);
  else if (courses.value.length < 15) void addCourse();
  else submitButton.value.focus();
}
async function calculate() {
  if (pending.value || !form.value.reportValidity()) return;
  pending.value = true; summary.value = null;
  const body = {courses:courses.value.map(course => ({subject:course.subject.trim() || null, units:Number(course.units), grade:Number(course.grade)}))};
  try {
    summary.value = await api('/gwa/calculate',{method:'POST',body,signal});
    await nextTick();
    if (!active()) return;
    result.value.focus({preventScroll:true});
    result.value.scrollIntoView({behavior:matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth',block:'nearest'});
  } catch (error) { if (active()) showNotice(error.message); }
  finally { pending.value = false; }
}
</script>
<template>
  <div class="page-heading"><div><h1>GWA Calculator</h1></div></div>
  <div class="gwa-layout"><form id="gwa-form" ref="form" class="panel" :aria-busy="pending || undefined" @submit.prevent="calculate"><fieldset id="gwa-fields" :disabled="pending"><legend class="sr-only">Courses for your GWA calculation</legend>
    <div class="section-heading course-heading"><h2>Your courses</h2><span id="course-count" class="muted" role="status">{{ courses.length }} / 15 courses</span></div>
    <div class="course-table-heading" aria-hidden="true"><span></span><div><span>Subject <small>(optional)</small></span><span>Units</span><span>Grade</span></div><span></span></div>
    <div id="course-rows"><div v-for="(course,index) in courses" :key="course.id" class="course-row" :data-course="index" @keydown="enter($event,index)">
      <div class="course-row-heading"><span class="course-number">{{ index+1 }}</span><button type="button" class="remove-course" :aria-label="'Remove course ' + (index+1)" :disabled="courses.length === 1" @click="remove(index)">×</button></div>
      <div class="course-inputs"><div class="subject-field"><label class="sr-only" :for="'subject-' + index">Subject <span class="muted">(optional)</span></label><input :id="'subject-' + index" v-model="course.subject" data-field="subject" :aria-label="'Subject for course ' + (index+1)" maxlength="120" placeholder="e.g. Mathematics" @input="summary = null"></div>
      <div><label class="sr-only" :for="'units-' + index">Units</label><input :id="'units-' + index" :value="course.units" data-field="units" :aria-label="'Units for course ' + (index+1)" type="number" inputmode="decimal" min="0.0001" max="99999999.9999" step="0.0001" required placeholder="3" @input="course.units = $event.target.value; summary = null"></div>
      <div><label class="sr-only" :for="'grade-' + index">Grade</label><input :id="'grade-' + index" :value="course.grade" data-field="grade" :aria-label="'Grade for course ' + (index+1)" type="text" inputmode="decimal" maxlength="16" required placeholder="1.75" @input="gradeInput($event,course)" @blur="gradeInput($event,course)"></div></div>
    </div></div>
    <div class="course-actions"><button type="button" id="add-course" class="secondary small" :disabled="courses.length >= 15" @click="addCourse">+ Add course</button><span class="hint">Up to 15 courses</span></div>
    <div class="form-actions"><button type="button" id="reset-gwa" class="secondary" @click="clear">Clear</button><button type="submit" id="calculate-gwa" ref="submitButton">{{ pending ? 'Calculating…' : "What's my GWA?" }}</button></div>
  </fieldset></form>
  <aside class="gwa-sidebar"><section v-if="!summary" id="gwa-placeholder" class="panel result-placeholder"><div class="result-symbol" aria-hidden="true">∑</div><h2>Your result belongs here.</h2><p class="muted">Add a course and calculate your GWA.</p></section>
    <section v-else id="gwa-result" ref="result" class="panel gwa-result" :class="{'is-failed':!summary.is_passing}" tabindex="-1" aria-label="Your GWA summary">
      <p class="eyebrow">Your GWA</p><h2 class="gwa-value">{{ summary.gwa_display }}</h2>
      <span class="result-badge">{{ summary.classification }}</span><div class="result-tools"><CopyButton :value="'GWA: ' + summary.gwa_display + ' · ' + summary.classification + ' · ' + summary.total_units + ' units'">Copy result</CopyButton></div>
      <div class="gwa-totals"><div><span class="muted">Courses</span><strong>{{ summary.course_count }}</strong></div><div><span class="muted">Total units</span><strong>{{ summary.total_units }}</strong></div></div>
      <div class="scale-heading"><h3>Grade scale</h3><strong>{{ percentage.toFixed(2) }}%</strong></div>
      <progress class="gwa-progress" max="100" :value="percentage" aria-label="Grade scale score"></progress><div class="scale-labels"><span>0%</span><span>100%</span></div>
      <p class="hint">1.00 = 100% · 5.00 = 0%. Visual grade scale.</p>
      <p v-if="summary.failed_course_count" class="course-warning">{{ summary.failed_course_count }} {{ summary.failed_course_count === 1 ? 'course is' : 'courses are' }} above 3.00. Honor standing here uses your overall GWA.</p>
    </section>
  </aside></div>
</template>
