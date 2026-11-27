import {onScopeDispose, ref} from 'vue';

// A reactive "now" that updates on every minute boundary (not on a drifting interval), and again when the
// tab becomes visible, since browsers throttle timers in background tabs.
export function useNow({target = typeof document === 'undefined' ? null : document} = {}) {
  const now = ref(new Date());
  let timer;
  function tick() {
    now.value = new Date();
    clearTimeout(timer);
    const current = now.value;
    timer = setTimeout(tick, 60000 - (current.getSeconds() * 1000 + current.getMilliseconds()) + 50);
  }
  const wake = () => { if (!target?.hidden) tick(); };
  tick();
  target?.addEventListener?.('visibilitychange', wake);
  onScopeDispose(() => { clearTimeout(timer); target?.removeEventListener?.('visibilitychange', wake); });
  return now;
}
