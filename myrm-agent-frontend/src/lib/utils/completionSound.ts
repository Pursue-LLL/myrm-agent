/**
 * Completion sound utilities.
 *
 * Plays a gentle two-note chime (G4→C5, perfect fourth) when the agent
 * finishes a response and the user is not looking at the page.
 * Uses Web Audio API — no external audio files needed.
 */

let audioCtx: AudioContext | null = null;

function getAudioContext(): AudioContext | null {
  if (audioCtx) return audioCtx;
  try {
    audioCtx = new AudioContext();
    return audioCtx;
  } catch {
    return null;
  }
}

/**
 * Play the completion chime if the page is not visible or focused.
 * Returns true if sound was played, false otherwise.
 */
export function playCompletionSound(): boolean {
  if (!document.hidden && document.hasFocus()) return false;

  const ctx = getAudioContext();
  if (!ctx) return false;
  if (ctx.state === 'suspended') {
    ctx.resume();
  }

  const now = ctx.currentTime;
  const masterGain = ctx.createGain();
  masterGain.gain.value = 0.15;
  masterGain.connect(ctx.destination);

  // Note 1: G4 (392 Hz), 0–120ms
  playNote(ctx, masterGain, 392, now, 0.12);
  // Note 2: C5 (523 Hz), 80–200ms (slight overlap for warmth)
  playNote(ctx, masterGain, 523, now + 0.08, 0.17);

  return true;
}

function playNote(ctx: AudioContext, destination: AudioNode, freq: number, startTime: number, duration: number): void {
  const osc = ctx.createOscillator();
  const noteGain = ctx.createGain();

  osc.type = 'sine';
  osc.frequency.value = freq;

  // Soft attack and release to avoid clicks
  noteGain.gain.setValueAtTime(0, startTime);
  noteGain.gain.linearRampToValueAtTime(1, startTime + 0.015);
  noteGain.gain.setValueAtTime(1, startTime + duration - 0.03);
  noteGain.gain.linearRampToValueAtTime(0, startTime + duration);

  osc.connect(noteGain);
  noteGain.connect(destination);
  osc.start(startTime);
  osc.stop(startTime + duration);
}
