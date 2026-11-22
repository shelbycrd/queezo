import {onScopeDispose, ref, shallowRef} from 'vue';
import {showNotice} from '../services/notice.js';

export function useLifetime() {
  const controller = new AbortController();
  onScopeDispose(() => controller.abort());
  return {signal:controller.signal, active:() => !controller.signal.aborted};
}

export function useResource(load) {
  const scope = useLifetime();
  const data = shallowRef(null), error = ref('');
  void load(scope.signal).then(value => {
    if (scope.active()) data.value = value;
  }).catch(failure => {
    if (scope.active()) { error.value = failure.message; showNotice(failure.message); }
  });
  return {...scope, data, error};
}

export function useEvent(target, type, handler) {
  target.addEventListener(type, handler);
  onScopeDispose(() => target.removeEventListener(type, handler));
}
