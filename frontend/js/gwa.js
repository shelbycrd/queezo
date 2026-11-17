import {api} from './api.js';
import {app, escape, mount} from './ui.js';
import {enhancePage} from './page-tools.js';
import {formatGradeDisplay, normalizeGradeInput} from './gwa-input.js';

const emptyCourse = () => ({subject:'', units:'', grade:''});

export function gwaPage(route) {
  let courses = [emptyCourse()];
  let pending = false;
  if (!mount(`<div class="page-heading"><div><h1>GWA Calculator</h1></div></div>
    <div class="gwa-layout"><form id="gwa-form" class="panel"><fieldset id="gwa-fields"><legend class="sr-only">Courses for your GWA calculation</legend>
      <div class="section-heading course-heading"><h2>Your courses</h2><span id="course-count" class="muted" role="status"></span></div>
      <div class="course-table-heading" aria-hidden="true"><span></span><div><span>Subject <small>(optional)</small></span><span>Units</span><span>Grade</span></div><span></span></div><div id="course-rows"></div>
      <div class="input-summary" id="course-live-totals" role="status"></div><div class="course-actions"><button type="button" id="add-course" class="secondary small">+ Add course</button><span class="hint">Up to 15 courses</span></div>
      <p id="gwa-error" class="inline-error" role="alert" hidden></p>
      <div class="form-actions"><button type="button" id="reset-gwa" class="secondary">Clear</button><button type="submit" id="calculate-gwa">What's my GWA?</button></div>
    </fieldset></form>
    <aside class="gwa-sidebar"><section id="gwa-placeholder" class="panel result-placeholder"><div class="result-symbol" aria-hidden="true">∑</div><h2>Your result belongs here.</h2><p class="muted">Add a course and calculate your GWA.</p></section>
      <section id="gwa-result" class="panel gwa-result" tabindex="-1" aria-label="Your GWA summary" hidden></section>
    </aside></div>`, route)) return;

  const form = app.querySelector('#gwa-form');
  const rows = form.querySelector('#course-rows');
  const fields = form.querySelector('#gwa-fields');
  const result = app.querySelector('#gwa-result');
  const placeholder = app.querySelector('#gwa-placeholder');
  const error = form.querySelector('#gwa-error');
  const submit = form.querySelector('#calculate-gwa');
  function validateGrade(input) {
    const text = input.value;
    const valid = !text || (/^\d+(?:\.\d{0,6})?$/.test(text) && Number(text) >= 1 && Number(text) <= 5);
    input.setCustomValidity(valid ? '' : 'Enter a grade from 1.00 to 5.00.');
  }

  function captureCourses() {
    courses = [...rows.querySelectorAll('[data-course]')].map(row => Object.fromEntries(
      ['subject','units','grade'].map(field => [field, row.querySelector(`[data-field="${field}"]`).value])
    ));
  }

  function updateTotals() {
    const entries = [...rows.querySelectorAll('[data-course]')];
    const units = entries.reduce((sum,row) => { const input=row.querySelector('[data-field="units"]'); return sum+(input.checkValidity() && input.value ? Number(input.value) : 0); },0);
    const ready = entries.filter(row => [...row.querySelectorAll('input')].every(input => input.checkValidity())).length;
    form.querySelector('#course-live-totals').textContent = `${ready} of ${entries.length} courses ready · ${Number(units.toFixed(4))} total units`;
  }
  function clearResult() {
    updateTotals();
    result.hidden = true;
    placeholder.hidden = false;
    error.hidden = true;
    error.textContent = '';
  }

  function renderRows() {
    rows.innerHTML = courses.map((course, index) => `<div class="course-row" data-course="${index}">
      <div class="course-row-heading"><span class="course-number">${index + 1}</span><button type="button" class="remove-course" data-remove="${index}" aria-label="Remove course ${index + 1}" ${courses.length === 1 ? 'disabled' : ''}>×</button></div>
      <div class="course-inputs"><div class="subject-field"><label class="sr-only" for="subject-${index}">Subject <span class="muted">(optional)</span></label><input id="subject-${index}" data-field="subject" aria-label="Subject for course ${index + 1}" maxlength="120" placeholder="e.g. Mathematics" value="${escape(course.subject)}"></div>
      <div><label class="sr-only" for="units-${index}">Units</label><input id="units-${index}" data-field="units" aria-label="Units for course ${index + 1}" type="number" inputmode="decimal" min="0.0001" max="99999999.9999" step="0.0001" required placeholder="3" value="${escape(course.units)}"></div>
      <div><label class="sr-only" for="grade-${index}">Grade</label><input id="grade-${index}" data-field="grade" aria-label="Grade for course ${index + 1}" type="text" inputmode="decimal" maxlength="16" required placeholder="1.75" value="${escape(course.grade)}"></div></div>
    </div>`).join('');
    form.querySelector('#course-count').textContent = `${courses.length} / 15 courses`;
    form.querySelector('#add-course').disabled = courses.length >= 15;
    rows.querySelectorAll('[data-field="grade"]').forEach(validateGrade);
    updateTotals();
  }

  function addCourse() {
    if (pending || courses.length >= 15) return;
    captureCourses();
    courses.push(emptyCourse());
    renderRows(); clearResult();
    rows.querySelector(`#subject-${courses.length - 1}`).focus();
  }
  form.querySelector('#add-course').addEventListener('click', addCourse);

  rows.addEventListener('click', event => {
    const remove = event.target.closest('[data-remove]');
    if (!remove || pending || courses.length <= 1) return;
    captureCourses();
    const index = Number(remove.dataset.remove);
    courses.splice(index, 1);
    renderRows(); clearResult();
    rows.querySelector(`#subject-${Math.min(index, courses.length - 1)}`).focus();
  });

  rows.addEventListener('input', event => {
    if (event.target.dataset.field === 'grade') {
      const input = event.target;
      const original = input.value;
      if (!event.inputType?.startsWith('delete') && !event.isComposing) {
        const normalized = normalizeGradeInput(original);
        if (normalized !== original) {
          input.value = normalized;
          input.setSelectionRange(normalized.length,normalized.length);
        }
      }
      validateGrade(input);
    }
    clearResult();
  });
  rows.addEventListener('focusout', event => {
    if (event.target.dataset.field === 'grade') { event.target.value = formatGradeDisplay(event.target.value); validateGrade(event.target); }
  });
  rows.addEventListener('keydown', event => {
    if (event.key !== 'Enter' || !event.target.matches('input') || event.isComposing || event.repeat || pending) return;
    event.preventDefault();
    const row = event.target.closest('[data-course]');
    if (!row) return;
    const invalid = [...row.querySelectorAll('input')].find(input => !input.checkValidity());
    if (invalid) { invalid.reportValidity(); invalid.focus(); return; }
    const next = row.nextElementSibling;
    if (next) next.querySelector('[data-field="subject"]').focus();
    else if (courses.length < 15) addCourse();
    else submit.focus();
  });
  form.querySelector('#reset-gwa').addEventListener('click', () => {
    if (pending) return;
    courses = [emptyCourse()];
    renderRows(); clearResult();
    rows.querySelector('#subject-0').focus();
  });

  form.addEventListener('submit', async event => {
    event.preventDefault();
    if (pending || !form.reportValidity()) return;
    captureCourses(); clearResult();
    pending = true;
    fields.disabled = true;
    form.setAttribute('aria-busy', 'true');
    submit.textContent = 'Calculating…';
    try {
      const summary = await api('/gwa/calculate', {method:'POST', body:{courses:courses.map(course => ({
        subject:course.subject.trim() || null, units:Number(course.units), grade:Number(course.grade),
      }))}});
      if (location.hash !== route || !form.isConnected) return;
      const percentage = Math.max(0, Math.min(100, summary.percentage));
      result.classList.toggle('is-failed', !summary.is_passing);
      result.innerHTML = `<p class="eyebrow">Your GWA</p><h2 class="gwa-value">${escape(summary.gwa_display)}</h2>
        <span class="result-badge">${escape(summary.classification)}</span><div class="result-tools"><button type="button" class="secondary small flat-button" data-copy="${escape(`GWA: ${summary.gwa_display} · ${summary.classification} · ${summary.total_units} units`)}">Copy result</button></div>
        <div class="gwa-totals"><div><span class="muted">Courses</span><strong>${summary.course_count}</strong></div><div><span class="muted">Total units</span><strong>${summary.total_units}</strong></div></div>
        <div class="scale-heading"><h3>Grade scale</h3><strong>${percentage.toFixed(2)}%</strong></div>
        <progress class="gwa-progress" max="100" value="${percentage}" aria-label="Grade scale score"></progress><div class="scale-labels"><span>0%</span><span>100%</span></div>
        <p class="hint">1.00 = 100% · 5.00 = 0%. Visual grade scale.</p>
        ${summary.failed_course_count ? `<p class="course-warning">${summary.failed_course_count} ${summary.failed_course_count === 1 ? 'course is' : 'courses are'} above 3.00. Honor standing here uses your overall GWA.</p>` : ''}
        `;
      enhancePage(result);
      placeholder.hidden = true;
      result.hidden = false;
      result.focus({preventScroll:true});
      result.scrollIntoView({behavior:matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth', block:'nearest'});
    } catch (failure) {
      if (location.hash !== route || !form.isConnected) return;
      error.textContent = failure.message;
      error.hidden = false;
    } finally {
      pending = false;
      fields.disabled = false;
      form.removeAttribute('aria-busy');
      submit.textContent = "What's my GWA?";
    }
  });

  renderRows();
}
