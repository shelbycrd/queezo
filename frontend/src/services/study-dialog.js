import {shallowRef} from 'vue';

export const studyRequest = shallowRef(null);
export function chooseStudy(deckId, {mode = 'classic'} = {}) {
  if (studyRequest.value) return Promise.resolve();
  return new Promise(resolve => { studyRequest.value = {deckId, mode, resolve}; });
}
export function chooseSharedStudy(token, {mode = 'classic'} = {}) {
  if (studyRequest.value) return Promise.resolve();
  return new Promise(resolve => {
    studyRequest.value = {token, mode, resolve};
  });
}

export function sharedMultipleChoiceRoute(sessionId, token) {
  return {name:'multiple-choice',params:{sessionId},query:{shared:token}};
}

export function closeStudyOptions(started = false) {
  const request = studyRequest.value;
  studyRequest.value = null;
  request?.resolve(started === true);
}
