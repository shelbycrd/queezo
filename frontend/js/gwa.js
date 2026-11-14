import {api} from './api.js';
import {app, escape, mount} from './ui.js';

const emptyCourse = () => ({subject:'', units:'', grade:''});

export function gwaPage(route) {
  let courses = [emptyCourse()];
  let pending = false;
  if (!mount(`<div class="page-heading"><div><p class="eyebrow">App 2 · GWA Calculator</p><h1>How are your grades looking?</h1><p class="muted">Add your courses. We'll do the weighted average.</p></div><span class="badge">1.00 is best · 3.00 is passing</span></div>
    <div class="gwa-layout"><form id="gwa-form" class="panel"><fieldset id="gwa-fields"><legend class="sr-only">Courses for your GWA calculation</legend>
      <div class="section-heading course-heading"><h2>Your courses</h2><span id="course-count" class="muted" role="status"></span></div>
      <p class="hint">Subject names are optional. Units and grades are required.</p><div id="course-rows"></div>
      <div class="course-actions"><button type="button" id="add-course" class="secondary small">+ Add course</button><span class="hint">Up to 15 courses</span></div>
      <p id="gwa-error" class="inline-error" role="alert" hidden></p>
      <div class="form-actions"><button type="button" id="reset-gwa" class="secondary">Clear</button><button type="submit" id="calculate-gwa">What's my GWA?</button></div>
      <p class="hint formula">GWA = sum of (grade × units) ÷ total units</p>
    </fieldset></form>
    <aside class="gwa-sidebar"><section id="gwa-placeholder" class="panel result-placeholder"><div class="result-symbol" aria-hidden="true">∑</div><h2>A clearer picture, in a moment.</h2><p class="muted">Enter at least one course and calculate to see your GWA, honor standing, and grade scale.</p></section>
      <section id="gwa-result" class="panel gwa-result" tabindex="-1" aria-label="Your GWA summary" hidden></section>
      <section class="panel honor-guide" aria-label="Honor bands"><h2>The honor bands</h2><dl><div><dt>First Honor</dt><dd>1.00–1.25</dd></div><div><dt>Second Honor</dt><dd>over 1.25–1.50</dd></div><div><dt>Third Honor</dt><dd>over 1.50–1.75</dd></div></dl><p class="hint">3.00 is just passing. Grades above 3.00 are failed. Honor labels use these GWA bands; your school may have additional rules.</p></section>
    </aside></div>`, route)) return;

  const form = app.querySelector('#gwa-form');
  const rows = form.querySelector('#course-rows');
  const fields = form.querySelector('#gwa-fields');
  const result = app.querySelector('#gwa-result');
  const placeholder = app.querySelector('#gwa-placeholder');
  const error = form.querySelector('#gwa-error');
  const submit = form.querySelector('#calculate-gwa');

  function captureCourses() {
    courses = [...rows.querySelectorAll('[data-course]')].map(row => Object.fromEntries(
      ['subject','units','grade'].map(field => [field, row.querySelector(`[data-field="${field}"]`).value])
    ));
  }

  function clearResult() {
    result.hidden = true;
    placeholder.hidden = false;
    error.hidden = true;
    error.textContent = '';
  }

  function renderRows() {
    rows.innerHTML = courses.map((course, index) => `<div class="course-row" data-course="${index}">
      <div class="course-row-heading"><span class="course-number">Course ${index + 1}</span><button type="button" class="remove-course" data-remove="${index}" aria-label="Remove course ${index + 1}" ${courses.length === 1 ? 'disabled' : ''}>Remove</button></div>
      <div class="course-inputs"><div class="subject-field"><label for="subject-${index}">Subject <span class="muted">(optional)</span></label><input id="subject-${index}" data-field="subject" aria-label="Subject for course ${index + 1}" maxlength="120" placeholder="e.g. Mathematics" value="${escape(course.subject)}"></div>
      <div><label for="units-${index}">Units</label><input id="units-${index}" data-field="units" aria-label="Units for course ${index + 1}" type="number" inputmode="decimal" min="0.0001" max="99999999.9999" step="0.0001" required placeholder="3" value="${escape(course.units)}"></div>
      <div><label for="grade-${index}">Grade</label><input id="grade-${index}" data-field="grade" aria-label="Grade for course ${index + 1}" type="number" inputmode="decimal" min="1" max="5" step="0.000001" required placeholder="1.75" value="${escape(course.grade)}"></div></div>
    </div>`).join('');
    form.querySelector('#course-count').textContent = `${courses.length} / 15 courses`;
    form.querySelector('#add-course').disabled = courses.length >= 15;
  }

  form.querySelector('#add-course').addEventListener('click', () => {
    if (pending || courses.length >= 15) return;
    captureCourses();
    courses.push(emptyCourse());
    renderRows(); clearResult();
    rows.querySelector(`#subject-${courses.length - 1}`).focus();
  });

  rows.addEventListener('click', event => {
    const remove = event.target.closest('[data-remove]');
    if (!remove || pending || courses.length <= 1) return;
    captureCourses();
    const index = Number(remove.dataset.remove);
    courses.splice(index, 1);
    renderRows(); clearResult();
    rows.querySelector(`#subject-${Math.min(index, courses.length - 1)}`).focus();
  });

  rows.addEventListener('input', clearResult);
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
        <span class="result-badge">${escape(summary.classification)}</span><p class="performance">${escape(summary.performance)}</p>
        <div class="gwa-totals"><div><span class="muted">Courses</span><strong>${summary.course_count}</strong></div><div><span class="muted">Total units</span><strong>${summary.total_units}</strong></div></div>
        <div class="scale-heading"><h3>Grade scale</h3><strong>${percentage.toFixed(2)}%</strong></div>
        <progress class="gwa-progress" max="100" value="${percentage}" aria-label="Grade scale score"></progress><div class="scale-labels"><span>0%</span><span>100%</span></div>
        <p class="hint">1.00 = 100% · 5.00 = 0%. A visual scale, not an official percentage grade.</p>
        ${summary.failed_course_count ? `<p class="course-warning">${summary.failed_course_count} ${summary.failed_course_count === 1 ? 'course is' : 'courses are'} above 3.00. Honor standing here uses your overall GWA.</p>` : ''}
        <p class="hint">GWA is rounded to two decimals. Honor standing uses the unrounded average.</p>`;
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
