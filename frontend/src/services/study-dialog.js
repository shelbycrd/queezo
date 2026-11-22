import {shallowRef} from 'vue';

export const studyRequest = shallowRef(null);
export function chooseStudy(deckId, {mode = 'classic'} = {}) {
  if (studyRequest.value) return Promise.resolve();
  return new Promise(resolve => { studyRequest.value = {deckId, mode, resolve}; });
}
export function closeStudyOptions(started = false) {
  const request = studyRequest.value;
  studyRequest.value = null;
  request?.resolve(started === true);
}
