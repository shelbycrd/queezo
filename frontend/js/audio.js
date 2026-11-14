let context;
const SOUND_KEY = 'queezo.button-sounds';
export function soundsEnabled() {
  try { return localStorage.getItem(SOUND_KEY) !== 'off'; } catch { return true; }
}
export function setSoundsEnabled(enabled) {
  try { localStorage.setItem(SOUND_KEY, enabled ? 'on' : 'off'); } catch { /* Keep the page usable without storage. */ }
}

// Create/resume during a user gesture; playback happens only after saving succeeds.
export function preparePageSound() {
  if (!soundsEnabled()) return;
  try {
    const Audio = window.AudioContext || window.webkitAudioContext;
    if (!Audio) return;
    context ||= new Audio();
    if (context.state === 'suspended') void context.resume().catch(() => {});
  } catch { /* Sound never prevents a card from being saved. */ }
}

export function playPageTurn() {
  if (!soundsEnabled() || !context || context.state !== 'running') return;
  try {
    const duration = 0.16;
    const buffer = context.createBuffer(1, Math.ceil(context.sampleRate * duration), context.sampleRate);
    const channel = buffer.getChannelData(0);
    for (let index = 0; index < channel.length; index++) channel[index] = (Math.random() * 2 - 1) * (1 - index / channel.length);
    const source = context.createBufferSource();
    source.buffer = buffer;
    const filter = context.createBiquadFilter();
    filter.type = 'bandpass'; filter.frequency.value = 1800; filter.Q.value = 0.5;
    const gain = context.createGain();
    gain.gain.setValueAtTime(0.001, context.currentTime);
    gain.gain.linearRampToValueAtTime(0.12, context.currentTime + 0.025);
    gain.gain.exponentialRampToValueAtTime(0.001, context.currentTime + duration);
    source.connect(filter); filter.connect(gain); gain.connect(context.destination);
    source.onended = () => { source.disconnect(); filter.disconnect(); gain.disconnect(); };
    source.start();
  } catch { /* The visual workflow remains available on muted/unsupported browsers. */ }
}

export function initButtonFeedback() {
  document.addEventListener('click', event => {
    const button = event.target.closest('button,.button,.photo-picker');
    if (!button || button.disabled) return;
    button.classList.add('is-pressed');
    setTimeout(() => button.classList.remove('is-pressed'), 130);
  }, {capture:true});
}
