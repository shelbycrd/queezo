import {test} from 'node:test';
import assert from 'node:assert/strict';
import {
  clockDialValue, convertDraft, conflictsForDraft, dayEntries, describeConflict, describeScheduleError, draftFromMinutes, expandRows, findConflicts,
  formatRange, formatTime, from12Hour, fromApiTime, groupMeetings, liveState, minutesOfDay, nextClassMessage, parseDraft, roomOf, scheduleStatus,
  statusMessage, to12Hour, toApiTime, validateRow, weekdayIndex,
} from '../src/services/schedule.js';

const at = (day, hour, minute = 0) => new Date(2026, 10, day, hour, minute); // Nov 23 2026 is a Monday
const subject = (id, name, meetings, extra = {}) => ({id, name, color:'blue', location:'', meetings, ...extra});
const meeting = (id, weekday, start, end, location = null) => ({id, weekday, start, end, location});

test('the selected day comes from the browser-local calendar, Monday first', () => {
  assert.equal(weekdayIndex(at(23, 9)), 0);
  assert.equal(weekdayIndex(at(27, 23, 59)), 4);
  assert.equal(weekdayIndex(at(28, 0, 1)), 5);
  assert.equal(weekdayIndex(at(29, 12)), 6);
  assert.equal(minutesOfDay(at(23, 13, 45)), 825);
});

test('the next-class summary skips Sunday and wraps to the next week', () => {
  const subjects = [
    subject(1, 'Physics', [meeting(1, 4, '15:00', '16:00')]),
    subject(2, 'Lab', [meeting(2, 6, '08:00', '09:00')]),
    subject(3, 'Biology', [meeting(3, 0, '09:30', '10:00')]),
  ];
  assert.equal(nextClassMessage(subjects, '12h', at(27, 14, 59)), 'Your next class is Physics at Fri, 3PM.');
  assert.equal(nextClassMessage(subjects, '24h', at(27, 15)), 'Your next class is Biology at Mon, 09:30.');
  assert.equal(nextClassMessage(subjects.slice(0, 2), '12h', at(27, 15)), 'Your next class is Physics at Fri, 3PM.');
  assert.equal(nextClassMessage([subjects[1]], '12h', at(29, 7)), '');
});

test('12-hour conversion handles midnight and noon and round-trips every minute', () => {
  assert.deepEqual(to12Hour(0), {hour:12, minute:0, period:'AM'});
  assert.deepEqual(to12Hour(30), {hour:12, minute:30, period:'AM'});
  assert.deepEqual(to12Hour(720), {hour:12, minute:0, period:'PM'});
  assert.deepEqual(to12Hour(750), {hour:12, minute:30, period:'PM'});
  assert.deepEqual(to12Hour(780), {hour:1, minute:0, period:'PM'});
  assert.deepEqual(to12Hour(1439), {hour:11, minute:59, period:'PM'});
  assert.equal(from12Hour(12, 0, 'AM'), 0);
  assert.equal(from12Hour(12, 0, 'PM'), 720);
  assert.equal(from12Hour(11, 59, 'PM'), 1439);
  for (let minutes = 0; minutes < 1440; minutes++) {
    const {hour, minute, period} = to12Hour(minutes);
    assert.equal(from12Hour(hour, minute, period), minutes);
    assert.equal(fromApiTime(toApiTime(minutes)), minutes);
  }
  assert.equal(fromApiTime('24:00'), null);
  assert.equal(fromApiTime('8:00'), null);
});

test('times display in the chosen format', () => {
  assert.equal(formatTime(0, '12h'), '12:00 AM');
  assert.equal(formatTime(720, '12h'), '12:00 PM');
  assert.equal(formatTime(810, '12h'), '1:30 PM');
  assert.equal(formatTime(0, '24h'), '00:00');
  assert.equal(formatTime(810, '24h'), '13:30');
  assert.equal(formatRange(480, 570, '12h'), '8:00 AM – 9:30 AM');
  assert.equal(formatRange(480, 570, '24h'), '08:00 – 09:30');
});

test('typed times are parsed per format and bad entries get clear errors', () => {
  assert.equal(parseDraft({text:'08:30', period:'AM'}, '12h').minutes, 510);
  assert.equal(parseDraft({text:'8', period:'PM'}, '12h').minutes, 1200);
  assert.equal(parseDraft({text:'12:00', period:'AM'}, '12h').minutes, 0);
  assert.equal(parseDraft({text:'12:00', period:'PM'}, '12h').minutes, 720);
  assert.equal(parseDraft({text:'13:00'}, '24h').minutes, 780);
  assert.equal(parseDraft({text:'00:00'}, '24h').minutes, 0);
  for (const text of ['13:00', '0:30', '9:60', 'ab', '', '1:2']) assert.ok(parseDraft({text, period:'AM'}, '12h').error, text);
  for (const text of ['24:00', '9:60', 'noon', '']) assert.ok(parseDraft({text}, '24h').error, text);
});

test('switching 12H/24H keeps every valid value and leaves unfinished entries alone', () => {
  for (const minutes of [0, 30, 480, 720, 750, 1380, 1439]) {
    const twelve = draftFromMinutes(minutes, '12h'), twentyFour = convertDraft(twelve, '12h', '24h');
    assert.equal(parseDraft(twentyFour, '24h').minutes, minutes);
    assert.deepEqual(convertDraft(twentyFour, '24h', '12h'), twelve);
  }
  assert.deepEqual(convertDraft({text:'12:00', period:'AM'}, '12h', '24h'), {text:'00:00', period:'AM'});
  assert.deepEqual(convertDraft({text:'12:00', period:'PM'}, '12h', '24h'), {text:'12:00', period:'PM'});
  const unfinished = {text:'8:', period:'PM'};
  assert.equal(convertDraft(unfinished, '12h', '24h'), unfinished);
});

test('the clock snaps minutes across the top of the dial and fine mode selects each minute', () => {
  const pickMinute = (minute, fine) => {
    const angle = minute / 60 * 2 * Math.PI;
    return clockDialValue(Math.sin(angle), -Math.cos(angle), 'minute', '12h', fine);
  };
  for (let minute = 0; minute < 60; minute++) {
    assert.equal(pickMinute(minute, false), Math.round(minute / 5) * 5 % 60);
    assert.equal(pickMinute(minute, true), minute);
  }
  assert.equal(clockDialValue(0, 0, 'minute', '12h'), null);
});

test('the 24-hour clock puts midnight and afternoon hours on the inner ring', () => {
  assert.equal(clockDialValue(0, -0.80, 'hour', '24h'), 12);
  assert.equal(clockDialValue(0, -0.52, 'hour', '24h'), 0);
  assert.equal(clockDialValue(-0.80, 0, 'hour', '24h'), 9);
  assert.equal(clockDialValue(-0.52, 0, 'hour', '24h'), 21);
  assert.equal(clockDialValue(-0.52, 0, 'hour', '12h'), 9);
});

test('a row needs days, valid times, and an end after the start (no overnight)', () => {
  const row = overrides => ({days:[0], location:'', start:{text:'08:00', period:'AM'}, end:{text:'09:30', period:'AM'}, ...overrides});
  const ok = validateRow(row(), '12h');
  assert.deepEqual([ok.start, ok.end, ok.valid], [480, 570, true]);
  assert.match(validateRow(row({days:[]}), '12h').errors.days, /at least one day/);
  assert.match(validateRow(row({start:{text:'', period:'AM'}}), '12h').errors.start, /Enter a time/);
  assert.match(validateRow(row({end:{text:'08:00', period:'AM'}}), '12h').errors.end, /after start time/);
  assert.match(validateRow(row({start:{text:'11:00', period:'PM'}, end:{text:'01:00', period:'AM'}}), '12h').errors.end, /Overnight/);
  assert.match(validateRow(row({end:{text:'12:00', period:'AM'}}), '12h').errors.end, /after start time/); // 12:00 AM is midnight
  assert.equal(validateRow(row({start:{text:'11:00', period:'PM'}, end:{text:'11:59', period:'PM'}}), '12h').valid, true);
  assert.equal(validateRow(row({start:{text:'00:00'}, end:{text:'00:30'}}), '24h').valid, true);
  assert.match(validateRow(row({location:'x'.repeat(81)}), '12h').errors.location, /80/);
});

test('one subject keeps several meetings and days that share a time become one editor row', () => {
  const data = subject(1, 'Data Structures', [meeting(10, 0, '08:00', '09:30'), meeting(11, 2, '13:00', '15:00', 'Computer Lab'), meeting(12, 4, '08:00', '09:30')]);
  const rows = groupMeetings(data.meetings);
  assert.equal(rows.length, 2);
  assert.deepEqual([rows[0].days, rows[0].start, rows[0].end, rows[0].ids], [[0, 4], 480, 570, {0:10, 4:12}]);
  assert.deepEqual([rows[1].days, rows[1].location], [[2], 'Computer Lab']);
  assert.deepEqual(expandRows(rows).map(item => [item.id, item.weekday, item.start, item.end, item.location]),
    [[10, 0, '08:00', '09:30', null], [12, 4, '08:00', '09:30', null], [11, 2, '13:00', '15:00', 'Computer Lab']]);
  rows[0].days = [0, 1]; // Friday deselected, Tuesday added
  const sent = expandRows(rows).filter(item => item.start === '08:00');
  assert.deepEqual(sent.map(item => [item.weekday, item.id]), [[0, 10], [1, undefined]]); // kept id reused, new day has none
});

test('a day lists classes chronologically with room overrides', () => {
  const a = subject(1, 'Biology', [meeting(1, 0, '13:00', '14:00')], {location:'Lab'});
  const b = subject(2, 'Algebra', [meeting(2, 0, '08:00', '09:00', 'Room 9'), meeting(3, 1, '08:00', '09:00')]);
  const entries = dayEntries([a, b], 0);
  assert.deepEqual(entries.map(entry => entry.subject.name), ['Algebra', 'Biology']);
  assert.deepEqual([roomOf(a, a.meetings[0]), roomOf(b, b.meetings[0]), roomOf(b, b.meetings[1])], ['Lab', 'Room 9', '']);
});

const sample = () => dayEntries([
  subject(1, 'Calculus', [meeting(1, 0, '08:00', '09:30')]), subject(2, 'Physics', [meeting(2, 0, '10:00', '11:30')]),
  subject(3, 'Seminar', [meeting(3, 0, '10:00', '10:30')]), // starts with Physics
  subject(4, 'Lab', [meeting(4, 0, '14:00', '15:00')]),
], 0);

test('the ongoing class is flagged and a class is over exactly when it ends', () => {
  const states = minutes => liveState(sample(), minutes);
  assert.deepEqual([states(480).status, states(480).byId[1]], ['ongoing', 'ongoing']); // at its start
  assert.equal(states(569).byId[1], 'ongoing');
  assert.equal(states(570).byId[1], 'done'); // at its end
  assert.equal(states(570).status, 'upcoming');
});

test('with nothing ongoing the next class (and every class starting then) is Up Next', () => {
  let state = liveState(sample(), 7 * 60);
  assert.deepEqual([state.status, state.byId[1], state.byId[2], state.byId[4]], ['upcoming', 'next', 'later', 'later']);
  state = liveState(sample(), 9 * 60 + 45); // between classes
  assert.deepEqual([state.byId[1], state.byId[2], state.byId[3], state.byId[4]], ['done', 'next', 'next', 'later']);
});

test('overlapping classes that are running are all marked ongoing', () => {
  const state = liveState(sample(), 10 * 60 + 15);
  assert.deepEqual([state.byId[2], state.byId[3], state.byId[4]], ['ongoing', 'ongoing', 'later']);
  assert.equal(state.byId[1], 'done');
  const later = liveState(sample(), 10 * 60 + 30);
  assert.deepEqual([later.byId[3], later.byId[2]], ['done', 'ongoing']); // the shorter one ends first
});

test('after the last class the day is finished, and an empty day has none', () => {
  assert.equal(liveState(sample(), 15 * 60).status, 'finished');
  assert.equal(liveState(sample(), 23 * 60 + 59).byId[4], 'done');
  assert.equal(liveState([], 600).status, 'none');
  const monday = at(23, 15, 30);
  assert.equal(statusMessage(scheduleStatus(sample(), 0, monday), 0, monday), 'All classes finished today.');
  assert.equal(statusMessage(scheduleStatus([], 0, monday), 0, monday), 'No classes today.');
  assert.equal(statusMessage(scheduleStatus([], 3, monday), 3, monday), 'No classes on Thursday.');
  assert.equal(statusMessage(scheduleStatus(sample(), 0, at(23, 9)), 0, at(23, 9)), '');
});

test('another day is shown without the live indicators of today', () => {
  const tuesdayView = scheduleStatus(sample(), 1, at(23, 10, 15)); // viewing Tuesday on Monday 10:15
  assert.deepEqual([tuesdayView.status, tuesdayView.byId], ['other', {}]);
  assert.equal(scheduleStatus(sample(), 0, at(23, 10, 15)).status, 'ongoing');
});

test('indicators move on as time passes', () => {
  const entries = sample(), mark = (minutes, id) => liveState(entries, minutes).byId[id];
  assert.equal(mark(479, 1), 'next');
  assert.equal(mark(480, 1), 'ongoing');
  assert.equal(mark(570, 1), 'done');
  assert.equal(mark(570, 2), 'next'); // Physics and Seminar start together
  assert.equal(mark(600, 2), 'ongoing');
});

test('overlaps are found per weekday; touching ends and other days are fine', () => {
  const calculus = subject(1, 'Calculus', [meeting(1, 0, '10:00', '11:30')]);
  const chemistry = subject(2, 'Chemistry', [meeting(2, 0, '11:30', '12:30'), meeting(3, 1, '10:00', '11:00')]);
  assert.deepEqual(findConflicts([calculus, chemistry]), []);
  const physics = subject(3, 'Physics', [meeting(4, 0, '11:00', '12:00')]);
  const found = findConflicts([calculus, chemistry, physics]);
  assert.deepEqual(found.map(item => [item.a.subject, item.b.subject]), [['Calculus', 'Physics'], ['Physics', 'Chemistry']]);
  assert.equal(findConflicts([subject(9, 'Seminar', [meeting(5, 0, '09:00', '10:00'), meeting(6, 0, '09:30', '10:30')])]).length, 1);
  assert.equal(describeConflict(found[0], '12h'), 'Mon: Calculus (10:00 AM – 11:30 AM) overlaps Physics (11:00 AM – 12:00 PM)');
  assert.equal(describeConflict(found[0], '24h'), 'Mon: Calculus (10:00 – 11:30) overlaps Physics (11:00 – 12:00)');
});

test('an edited draft replaces its saved version when checking for overlaps', () => {
  const calculus = subject(1, 'Calculus', [meeting(1, 0, '10:00', '11:30')]);
  const physics = subject(2, 'Physics', [meeting(2, 0, '13:00', '14:00')]);
  const moved = {id:2, name:'Physics', meetings:[meeting(-1, 0, '11:00', '12:00')]};
  assert.equal(conflictsForDraft(moved, [calculus, physics]).length, 1);
  assert.equal(conflictsForDraft({id:2, name:'Physics', meetings:[meeting(-1, 0, '12:00', '13:00')]}, [calculus, physics]).length, 0);
  assert.equal(conflictsForDraft({id:0, name:'New', meetings:[meeting(-1, 0, '13:30', '15:00')]}, [calculus, physics]).length, 1);
});

test('server validation messages become readable', () => {
  assert.equal(describeScheduleError('body.meetings.1.end: Value error, End time must be after start time.'),
    'Meeting 2 end: End time must be after start time.');
  assert.equal(describeScheduleError('body.name: String should have at least 1 character'), 'name: String should have at least 1 character');
  assert.equal(describeScheduleError(''), 'The schedule could not be saved.');
});
