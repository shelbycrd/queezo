// Class schedule helpers: day and time conversion, live "Now / Up Next" state, and overlap detection.
// Times are minutes after midnight in memory and "HH:MM" (24-hour) on the wire, whatever the display format.

export const WEEKDAYS = [
  {key:0, short:'Mon', long:'Monday'}, {key:1, short:'Tue', long:'Tuesday'}, {key:2, short:'Wed', long:'Wednesday'},
  {key:3, short:'Thu', long:'Thursday'}, {key:4, short:'Fri', long:'Friday'}, {key:5, short:'Sat', long:'Saturday'},
  {key:6, short:'Sun', long:'Sunday'},
];
export const SCHEDULE_DAYS = WEEKDAYS.slice(0, 6);
export const COLORS = [
  {key:'blue', label:'Blue'}, {key:'mint', label:'Mint'}, {key:'lilac', label:'Lilac'}, {key:'peach', label:'Peach'},
  {key:'rose', label:'Rose'}, {key:'butter', label:'Butter'}, {key:'sky', label:'Sky'}, {key:'sage', label:'Sage'},
];
export const MAX_MEETINGS_PER_SUBJECT = 14;
export const NAME_LIMIT = 80, CODE_LIMIT = 20, ROOM_LIMIT = 80;

// Monday is 0, from the browser-local calendar day.
export const weekdayIndex = (date = new Date()) => (date.getDay() + 6) % 7;
export const minutesOfDay = (date = new Date()) => date.getHours() * 60 + date.getMinutes();

// ---- Time conversion -------------------------------------------------------------------------

const pad = value => String(value).padStart(2, '0');
export const toApiTime = minutes => pad(Math.floor(minutes / 60)) + ':' + pad(minutes % 60);
export function fromApiTime(text) {
  const match = /^([01]\d|2[0-3]):([0-5]\d)$/.exec(String(text));
  return match ? Number(match[1]) * 60 + Number(match[2]) : null;
}

// 12 AM is hour 0 and 12 PM is hour 12; 1–11 gain 12 hours in the afternoon.
export function to12Hour(minutes) {
  const hour = Math.floor(minutes / 60);
  return {hour:hour % 12 || 12, minute:minutes % 60, period:hour < 12 ? 'AM' : 'PM'};
}
export function from12Hour(hour, minute, period) {
  return ((hour % 12) + (period === 'PM' ? 12 : 0)) * 60 + minute;
}

export function formatTime(minutes, format) {
  if (format === '24h') return toApiTime(minutes);
  const {hour, minute, period} = to12Hour(minutes);
  return hour + ':' + pad(minute) + ' ' + period;
}
export const formatRange = (start, end, format) => formatTime(start, format) + ' – ' + formatTime(end, format);

// Editor field drafts hold what the user typed: {text:'08:30', period:'AM'}. The period only matters in 12H.
export function draftFromMinutes(minutes, format) {
  const {hour, minute, period} = to12Hour(minutes);
  return {text:format === '24h' ? toApiTime(minutes) : pad(hour) + ':' + pad(minute), period};
}

export function parseDraft(draft, format) {
  const match = /^(\d{1,2})(?::(\d{2}))?$/.exec(String(draft?.text ?? '').trim());
  const hour = match ? Number(match[1]) : NaN, minute = match?.[2] === undefined ? 0 : Number(match?.[2]);
  if (format === '24h') {
    if (!match || hour > 23 || minute > 59) return {error:'Enter a time from 00:00 to 23:59.'};
    return {minutes:hour * 60 + minute};
  }
  if (!match || hour < 1 || hour > 12 || minute > 59) return {error:'Enter a time from 1:00 to 12:59, then choose AM or PM.'};
  return {minutes:from12Hour(hour, minute, draft.period === 'PM' ? 'PM' : 'AM')};
}

// Switching 12H/24H re-expresses every valid entry in the new format; an unfinished entry is left as typed.
export function convertDraft(draft, from, to) {
  const parsed = parseDraft(draft, from);
  return parsed.error ? draft : draftFromMinutes(parsed.minutes, to);
}

// Coordinates are relative to the center, with the face's edge at radius 1.
export function clockDialValue(x, y, mode, format, fine = false) {
  const radius = Math.hypot(x, y);
  if (radius < 0.12) return null;

  const turn = 1 + Math.atan2(x, -y) / (2 * Math.PI);
  if (mode === 'minute') {
    const step = fine ? 1 : 5;
    const marks = 60 / step;
    return (Math.round(turn * marks) % marks) * step;
  }

  const hour = Math.round(turn * 12) % 12;
  if (format === '24h' && radius < 0.66) return hour === 0 ? 0 : hour + 12;
  return hour || 12;
}

// ---- Editor rows: several days can share one time slot -----------------------------------------

export function groupMeetings(meetings) {
  const rows = new Map();
  for (const meeting of meetings) {
    const start = fromApiTime(meeting.start), end = fromApiTime(meeting.end), location = meeting.location || '';
    const key = start + '-' + end + '-' + location;
    if (!rows.has(key)) rows.set(key, {days:[], ids:{}, start, end, location});
    const row = rows.get(key);
    row.days.push(meeting.weekday);
    row.ids[meeting.weekday] = meeting.id;
  }
  return [...rows.values()].map(row => ({...row, days:row.days.sort((a, b) => a - b)}));
}

export function expandRows(rows) {
  return rows.flatMap(row => [...row.days].sort((a, b) => a - b).map(weekday => ({
    ...(row.ids?.[weekday] ? {id:row.ids[weekday]} : {}), weekday, start:toApiTime(row.start), end:toApiTime(row.end),
    location:row.location.trim() || null,
  })));
}

// Validates one editor row. start and end are minutes when their text is valid.
export function validateRow(row, format) {
  const errors = {}, start = parseDraft(row.start, format), end = parseDraft(row.end, format);
  if (!row.days.length) errors.days = 'Choose at least one day.';
  if (start.error) errors.start = start.error;
  if (end.error) errors.end = end.error;
  if (!errors.start && !errors.end && end.minutes <= start.minutes) {
    errors.end = 'End time must be after start time. Overnight classes aren’t supported yet.';
  }
  if (row.location.length > ROOM_LIMIT) errors.location = `Use ${ROOM_LIMIT} characters or fewer.`;
  return {errors, start:start.minutes ?? null, end:end.minutes ?? null, valid:!Object.keys(errors).length};
}

// ---- Day listing and live state ---------------------------------------------------------------------

export const roomOf = (subject, meeting) => meeting.location || subject.location || '';

export function dayEntries(subjects, weekday) {
  return subjects.flatMap(subject => subject.meetings.filter(meeting => meeting.weekday === weekday).map(meeting => ({
    id:meeting.id, subject, meeting, start:fromApiTime(meeting.start), end:fromApiTime(meeting.end),
  }))).sort((a, b) => a.start - b.start || a.end - b.end || a.subject.name.localeCompare(b.subject.name) || a.id - b.id);
}

export function nextClassMessage(subjects, format, now = new Date()) {
  const today = weekdayIndex(now), currentMinute = minutesOfDay(now);
  // Include this weekday next week after today's final meeting.
  for (let offset = 0; offset <= WEEKDAYS.length; offset++) {
    const weekday = (today + offset) % WEEKDAYS.length;
    if (weekday >= SCHEDULE_DAYS.length) continue;
    const entry = dayEntries(subjects, weekday).find(item => offset > 0 || item.start > currentMinute);
    if (!entry) continue;
    const time = formatTime(entry.start, format).replace(':00 ', ' ').replace(' ', '');
    return `Your next class is ${entry.subject.name} at ${WEEKDAYS[weekday].short}, ${time}.`;
  }
  return '';
}

// Live state for one day's entries at nowMinutes: everything running now, else the next start (all that share it).
export function liveState(entries, nowMinutes) {
  const byId = {};
  if (!entries.length) return {status:'none', byId};
  const ongoing = entries.filter(entry => entry.start <= nowMinutes && nowMinutes < entry.end);
  const upcoming = entries.filter(entry => entry.start > nowMinutes);
  const nextStart = upcoming.length ? Math.min(...upcoming.map(entry => entry.start)) : null;
  for (const entry of entries) {
    byId[entry.id] = ongoing.includes(entry) ? 'ongoing' : entry.end <= nowMinutes ? 'done'
      : !ongoing.length && entry.start === nextStart ? 'next' : 'later';
  }
  return {status:ongoing.length ? 'ongoing' : upcoming.length ? 'upcoming' : 'finished', byId};
}

// Live indicators apply only to today's list; another day is shown without them.
export function scheduleStatus(entries, selectedDay, now = new Date()) {
  if (selectedDay !== weekdayIndex(now)) return {status:entries.length ? 'other' : 'none', byId:{}};
  return liveState(entries, minutesOfDay(now));
}

export function statusMessage(state, selectedDay, now = new Date()) {
  const isToday = selectedDay === weekdayIndex(now);
  if (state.status === 'none') return isToday ? 'No classes today.' : `No classes on ${WEEKDAYS[selectedDay].long}.`;
  if (state.status === 'finished') return 'All classes finished today.';
  return '';
}

// ---- Overlaps -------------------------------------------------------------------------------------------

// Two meetings on one weekday overlap when each starts before the other ends; touching ends do not.
export function findConflicts(subjects) {
  const found = [];
  for (const weekday of WEEKDAYS.map(day => day.key)) {
    const slots = dayEntries(subjects, weekday);
    slots.forEach((slot, index) => {
      for (const other of slots.slice(index + 1)) {
        if (other.start >= slot.end) break;
        found.push({weekday, a:conflictSide(slot), b:conflictSide(other)});
      }
    });
  }
  return found;
}
const conflictSide = slot => ({subject_id:slot.subject.id, subject:slot.subject.name, meeting_id:slot.id,
  start:slot.meeting.start, end:slot.meeting.end});

// Draft overlaps for the editor: the subject being edited replaces its saved version.
export function conflictsForDraft(draft, subjects) {
  const id = draft.id ?? 0;
  return findConflicts([draft, ...subjects.filter(subject => subject.id !== id)])
    .filter(item => item.a.subject_id === id || item.b.subject_id === id);
}

export function describeConflict(conflict, format) {
  const side = part => `${part.subject} (${formatRange(fromApiTime(part.start), fromApiTime(part.end), format)})`;
  return `${WEEKDAYS[conflict.weekday].short}: ${side(conflict.a)} overlaps ${side(conflict.b)}`;
}

// Server validation details name fields like "body.meetings.0.end"; turn them into plain sentences.
export function describeScheduleError(message) {
  return String(message || 'The schedule could not be saved.')
    .replace(/body\.meetings\.(\d+)\.(start|end|weekday|location)\b[^:]*: (?:Value error, )?/g,
      (_, index, field) => `Meeting ${Number(index) + 1} ${field === 'weekday' ? 'day' : field}: `)
    .replace(/body\.meetings\b[^:]*: (?:Value error, )?/g, 'Meetings: ')
    .replace(/body\.(name|code|instructor|location|color)\b[^:]*: (?:Value error, )?/g, (_, field) => `${field}: `);
}
