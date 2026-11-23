import {shallowRef} from 'vue';

export const noticeDuration = 5000;
export const notice = shallowRef(null);
export function showNotice(message, success = false) {
  notice.value = message ? {message, success} : null;
}

export async function copyText(value) {
  try {
    await navigator.clipboard.writeText(value);
    showNotice('Copied ✓', true);
  } catch {
    showNotice('Copy unavailable. Select the value and copy it manually.');
  }
}
