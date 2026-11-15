import test from 'node:test';
import assert from 'node:assert/strict';

test('Pomodoro audio uses the supplied file, skips silence, caches decoding, and respects mute', async () => {
  const old = Object.fromEntries(['window','fetch','localStorage'].map(key=>[key,Object.getOwnPropertyDescriptor(globalThis,key)]));
  let muted = false, fetches = 0;
  const starts = [];
  const samples = new Float32Array(500); samples[105]=1;
  class Audio {
    state='running'; currentTime=10;
    decodeAudioData() { return Promise.resolve({sampleRate:1000,duration:.5,getChannelData:()=>samples}); }
    createBufferSource() { return {connect(){},disconnect(){},start(...args){starts.push(args);}}; }
    createGain() { return {gain:{setValueAtTime(){},linearRampToValueAtTime(){}},connect(){},disconnect(){}}; }
  }
  Object.defineProperty(globalThis,'window',{configurable:true,value:{AudioContext:Audio}});
  Object.defineProperty(globalThis,'localStorage',{configurable:true,value:{getItem:()=>muted?'off':'on'}});
  Object.defineProperty(globalThis,'fetch',{configurable:true,value:async url=>{assert.equal(url,'/audio/creamy-keyboard.mp3');fetches++;return {ok:true,arrayBuffer:async()=>new ArrayBuffer(1)};}});
  try {
    const {playTimerPress} = await import('../js/audio.js');
    await playTimerPress(); await playTimerPress();
    assert.equal(fetches,1);
    assert.equal(starts.length,2);
    assert.ok(Math.abs(starts[0][1]-.097)<.0001);
    assert.equal(starts[0][2],.24);
    muted=true; await playTimerPress();
    assert.equal(starts.length,2);
  } finally {
    for(const [key,descriptor] of Object.entries(old)) { if(descriptor)Object.defineProperty(globalThis,key,descriptor);else delete globalThis[key]; }
  }
});
