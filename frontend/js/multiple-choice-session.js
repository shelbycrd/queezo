import {api} from './api.js';

export const SESSION_LABELS = {
  preparing:'Preparing', failed:'Preparation needs attention', active:'In progress',
  completed:'Completed', cancelled:'Cancelled', expired:'Expired',
};

export function scoreSummary(session) {
  const {correct, answered} = session;
  return {
    correct,
    incorrect: answered - correct,
    total: session.progress.ready,
    accuracy: answered ? Math.round(correct / answered * 100) : null,
  };
}

export function multipleChoiceSession(sessionId, {
  update, active = () => true, request = api,
  setTimer = setTimeout, clearTimer = clearTimeout,
}) {
  const path = `/multiple-choice/${encodeURIComponent(sessionId)}`;
  const reads = new AbortController();
  const view = {session:null, question:null, grade:null, pending:null, problem:null, message:''};
  let version = 0;
  let timer;

  const current = token => !reads.signal.aborted && active() && token === version;
  const publish = () => update({...view});
  function clearPoll() {
    clearTimer(timer);
    timer = undefined;
  }
  function pollLater(token) {
    if (current(token) && view.session?.status === 'preparing' && !view.problem) {
      timer = setTimer(() => void poll(), 1500);
    }
  }
  async function readState(token, savedSession) {
    let session = savedSession ?? await request(path, {signal:reads.signal});
    if (!current(token)) return;
    let question = null;
    if (session.status === 'active') {
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
    if (current(token)) Object.assign(view, {session, question, grade:null});
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
      pollLater(token);
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
          if (current(token)) view.message = error.status === 409 ? 'The session changed. Showing your latest saved progress.' : '';
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
        pollLater(token);
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
        Object.assign(view, {grade:null, question:null});
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
