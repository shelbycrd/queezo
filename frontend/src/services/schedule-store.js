import {computed, shallowRef, watch} from 'vue';
import {api} from '../../js/api.js';
import {account} from './session.js';

// Shared snapshot of the signed-in user's schedule, used by the Home card and the schedule page.
export const schedule = shallowRef(null);
export const timeFormat = computed(() => schedule.value?.time_format ?? '12h');

let token = 0; // Ignore any response older than the newest request, so a slow refresh cannot undo a save.
watch(() => account.value?.id, () => { token++; schedule.value = null; });

export async function loadSchedule() {
  const mine = ++token, owner = account.value?.id;
  const view = await api('/schedule');
  if (mine === token && owner === account.value?.id) schedule.value = view;
  return view;
}

function adopt(response) {
  token++;
  const {subject_id, warnings, ...view} = response;
  schedule.value = view;
  return {subjectId:subject_id, warnings:warnings ?? []};
}

export async function saveSubject(id, body) {
  const owner = account.value?.id;
  const response = await api(id ? '/schedule/subjects/' + id : '/schedule/subjects', {method:id ? 'PUT' : 'POST', body});
  if (owner !== account.value?.id) return {subjectId:null, warnings:[]};
  return adopt(response);
}

export async function deleteSubject(id) {
  const owner = account.value?.id;
  const response = await api('/schedule/subjects/' + id, {method:'DELETE'});
  if (owner === account.value?.id) adopt(response);
}

export const loadScheduleHistory = signal => api('/schedule/history', {signal});
export const loadScheduleArchive = (id, signal) => api('/schedule/history/' + id, {signal});

export async function clearSchedule() {
  const owner = account.value?.id;
  const response = await api('/schedule', {method:'DELETE'});
  if (owner === account.value?.id) adopt(response);
}

export async function restoreSchedule(id) {
  const owner = account.value?.id;
  const response = await api('/schedule/history/' + id + '/restore', {method:'POST'});
  if (owner === account.value?.id) adopt(response);
}

// The 12H/24H choice applies immediately everywhere and is saved to the account for later sessions.
export async function setTimeFormat(format) {
  if (!schedule.value || format === schedule.value.time_format) return;
  const previous = schedule.value, mine = ++token;
  schedule.value = {...previous, time_format:format};
  try { await api('/schedule/preferences', {method:'PUT', body:{time_format:format}}); }
  catch (error) {
    if (mine === token && schedule.value) schedule.value = {...schedule.value, time_format:previous.time_format};
    throw error;
  }
}
