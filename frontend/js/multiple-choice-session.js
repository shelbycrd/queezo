import {api} from './api.js';

export const SESSION_LABELS = {
  preparing:'Preparing', failed:'Preparation needs attention', active:'In progress',
  completed:'Completed', cancelled:'Cancelled', expired:'Expired',
};

export function scoreSummary(session) {
  const {correct, answered} = session;
  const attempted = answered + (session.timed_out ?? 0);
  return {
    correct,
    incorrect: answered - correct,
    total: session.progress.ready,
    accuracy: attempted ? Math.round(correct / attempted * 100) : null,
  };
}

export function multipleChoiceSession(sessionId, {
  update, active = () => true, request = api,
  setTimer = setTimeout, clearTimer = clearTimeout, now = Date.now,
}) {
  const path = `/multiple-choice/${encodeURIComponent(sessionId)}`;
  const reads = new AbortController();
  const view = {session:null, question:null, grade:null, clock:null, pending:null, problem:null, message:''};
  let version = 0;
  let timer;

  const current = token => !reads.signal.aborted && active() && token === version;
  const publish = () => update({...view});
  function clearPoll() {
    clearTimer(timer);
    timer = undefined;
  }
  function schedule(token) {
    if (!current(token) || view.problem) return;
    if (view.session?.status === 'preparing') {
      timer = setTimer(() => void poll(), 1500);
    } else if (view.session?.status === 'active' && view.clock &&
               (!view.grade || view.session.timing.scope === 'deck')) {
      timer = setTimer(() => void run('clock', readState), Math.max(0, view.clock - now()));
    }
  }
  async function readState(token, savedSession) {
    let session = savedSession ?? await request(path, {signal:reads.signal});
    if (!current(token)) return;
    let question = null;
    let clock = null;
    if (session.status === 'active' && session.timing) {
      const opened = await request(path + '/question', {method:'POST'});
      session = opened.session;
      question = opened.question;
      if (Number.isFinite(opened.remaining_ms)) clock = now() + opened.remaining_ms;
    } else if (session.status === 'active') {
      try {
        question = await request(path + '/question', {signal:reads.signal});
      } catch (error) {
        if (!current(token) || ![409,410].includes(error.status)) throw error;
        // Another tab may finish or cancel between the status and question requests.
        session = await request(path, {signal:reads.signal});
        if (current(token) && session.status === 'active') {
          question = await request(path + '/question', {signal:reads.signal});
        }
      }
    }
    if (current(token)) {
      if (session.status === 'active' && session.timed_out > (view.session?.timed_out ?? 0)) {
        view.message = 'Time ran out. The missed question was skipped.';
      }
      Object.assign(view, {session, question, clock, grade:null});
    }
  }
  function report(error) {
    view.problem = {status:error.status, message:error.message};
  }
  async function poll() {
    const token = version;
    if (!current(token) || view.pending) return;
    try {
      const session = await request(path, {signal:reads.signal});
      if (!current(token)) return;
      const changed = session.status !== view.session.status ||
        session.progress.completed !== view.session.progress.completed;
      if (changed) {
        await readState(token, session);
        if (current(token)) publish();
      }
    } catch (error) {
      if (current(token)) {
        report(error);
        publish();
      }
    } finally {
      schedule(token);
    }
  }
  async function run(action, operation) {
    if (!current(version) || view.pending) return;
    clearPoll();
    const token = ++version;
    Object.assign(view, {pending:action, problem:null, message:''});
    publish();
    try {
      await operation(token);
    } catch (error) {
      if (!current(token)) return;
      if (action !== 'refresh' && [409,410].includes(error.status)) {
        try {
          await readState(token);
          if (current(token) && !view.message && error.status === 409 && view.session?.status === 'active') {
            view.message = 'The session changed. Showing your latest saved progress.';
          }
        } catch (refreshError) {
          if (current(token)) report(refreshError);
        }
      } else {
        report(error);
      }
    } finally {
      if (current(token)) {
        view.pending = null;
        publish();
        schedule(token);
      }
    }
  }
  return {
    refresh: () => run('refresh', readState),
    answer(optionId) {
      if (view.session?.status !== 'active' || view.grade || view.problem ||
          !view.question?.options.some(option => option.id === optionId)) return;
      const body = {question_id:view.question.id, option_id:optionId};
      return run('answer', async token => {
        const grade = await request(path + '/answer', {method:'POST', body});
        if (current(token)) Object.assign(view, {grade, session:grade.session});
      });
    },
    next() {
      if (!view.grade) return;
      if (view.session.status === 'completed') {
        Object.assign(view, {grade:null, question:null, clock:null});
        publish();
      } else {
        return run('next', readState);
      }
    },
    transition(action) {
      if (!['retry','continue','cancel'].includes(action) || view.problem) return;
      return run(action, async token => {
        const session = await request(`${path}/${action}`, {method:'POST'});
        if (current(token)) await readState(token, session);
      });
    },
    stop() {
      ++version;
      clearPoll();
      reads.abort();
    },
  };
}
