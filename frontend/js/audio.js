let context;
let timerBuffer;
let timerLoad;
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

export function playAnswerSound(correct, delay = 0) {
  if (correct) playTones([659.25, 880, 1108.73], 'sine', .065, .2, .12, delay);
  else playTones([246.94, 185], 'triangle', .09, .14, .12, delay);
}

export function playRoomLockSound() {
  playTones([520], 'sine', 0, .09, .055);
}

function playTones(notes, type, interval, duration, volume, delay = 0) {
  if (!soundsEnabled() || context?.state !== 'running') return;
  try {
    const start = context.currentTime + delay;
    notes.forEach((pitch, index) => {
      const time = start + index * interval;
      const end = time + duration;
      const tone = context.createOscillator();
      const gain = context.createGain();
      tone.type = type;
      tone.frequency.value = pitch;
      gain.gain.setValueAtTime(0.001, time);
      gain.gain.linearRampToValueAtTime(volume, time + 0.012);
      gain.gain.exponentialRampToValueAtTime(0.001, end);
      tone.connect(gain);
      gain.connect(context.destination);
      tone.onended = () => { tone.disconnect(); gain.disconnect(); };
      tone.start(time);
      tone.stop(end);
    });
  } catch { /* Feedback still appears when audio is unavailable. */ }
}

export async function playTimerPress() {
  if (!soundsEnabled()) return;
  preparePageSound();
  if (!context) return;
  try {
    timerLoad ||= fetch('/audio/creamy-keyboard.mp3').then(response => {
      if (!response.ok) throw new Error('Audio unavailable');
      return response.arrayBuffer();
    }).then(bytes => context.decodeAudioData(bytes)).then(buffer => {
      const samples = buffer.getChannelData(0);
      let peak = 0;
      for (const sample of samples) peak = Math.max(peak,Math.abs(sample));
      const onset = samples.findIndex(sample => Math.abs(sample) >= Math.max(0.008,peak * 0.18));
      const offset = Math.max(0,onset / buffer.sampleRate - 0.008);
      timerBuffer = {buffer,offset,duration:Math.min(0.24,buffer.duration-offset)};
      return timerBuffer;
    });
    const clip = await timerLoad;
    if (!soundsEnabled() || context.state !== 'running' || clip.duration <= 0) return;
    const source = context.createBufferSource(); source.buffer = clip.buffer;
    const gain = context.createGain(); const now = context.currentTime;
    gain.gain.setValueAtTime(0.55,now);
    gain.gain.setValueAtTime(0.55,now + Math.max(0,clip.duration - 0.025));
    gain.gain.linearRampToValueAtTime(0,now + clip.duration);
    source.connect(gain); gain.connect(context.destination);
    source.onended = () => { source.disconnect(); gain.disconnect(); };
    source.start(now,clip.offset,clip.duration);
  } catch { timerLoad = null; /* Audio never blocks the timer. */ }
}

let lastChatPop = -Infinity;
export function playChatPop() {
  if (!soundsEnabled() || context?.state !== 'running') return;
  const now = context.currentTime;
  if (now - lastChatPop < .4) return;
  try {
    const tone = context.createOscillator();
    const volume = context.createGain();
    tone.frequency.setValueAtTime(680,now);
    tone.frequency.exponentialRampToValueAtTime(335,now + .065);
    volume.gain.setValueAtTime(.001,now);
    volume.gain.linearRampToValueAtTime(.032,now + .009);
    volume.gain.exponentialRampToValueAtTime(.001,now + .085);
    tone.connect(volume);
    volume.connect(context.destination);
    tone.onended = () => { tone.disconnect(); volume.disconnect(); };
    tone.start(now);
    tone.stop(now + .085);
    lastChatPop = now;
  } catch { /* Chat remains available when browser audio is blocked. */ }
}
