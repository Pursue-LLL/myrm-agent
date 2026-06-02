import { describe, it, expect, beforeEach } from 'vitest';
import { SpeechVisualSession } from '@/lib/vision/speechVisualSession';

describe('SpeechVisualSession', () => {
  let session: SpeechVisualSession;

  beforeEach(() => {
    session = new SpeechVisualSession();
  });

  it('returns null when endSpeech called without beginSpeech', () => {
    expect(session.endSpeech()).toBeNull();
  });

  it('returns a valid window after begin + end', () => {
    session.beginSpeech(5000);
    const window = session.endSpeech(8000);

    expect(window).not.toBeNull();
    expect(window!.speechStartAt).toBe(5000);
    expect(window!.speechEndAt).toBe(8000);
    expect(window!.frameWindowStartAt).toBeLessThan(window!.speechStartAt);
    expect(window!.frameWindowEndAt).toBeGreaterThan(window!.speechEndAt);
  });

  it('uses preRoll and postRoll correctly', () => {
    session.beginSpeech(10000);
    const window = session.endSpeech(15000, 1000, 500);

    expect(window!.frameWindowStartAt).toBe(10000 - 1000);
    expect(window!.frameWindowEndAt).toBe(15000 + 500);
    expect(window!.preRollMs).toBe(1000);
    expect(window!.postRollMs).toBe(500);
  });

  it('uses default preRoll/postRoll (500/300)', () => {
    session.beginSpeech(10000);
    const window = session.endSpeech(15000);

    expect(window!.frameWindowStartAt).toBe(10000 - 500);
    expect(window!.frameWindowEndAt).toBe(15000 + 300);
  });

  it('does not update startAt on repeated beginSpeech calls', () => {
    session.beginSpeech(5000);
    session.beginSpeech(6000);
    const window = session.endSpeech(8000);

    expect(window!.speechStartAt).toBe(5000);
  });

  it('reset clears state so endSpeech returns null', () => {
    session.beginSpeech(1000);
    session.reset();
    expect(session.endSpeech()).toBeNull();
  });

  it('can begin a new session after reset', () => {
    session.beginSpeech(1000);
    session.reset();
    session.beginSpeech(5000);
    const window = session.endSpeech(7000);

    expect(window!.speechStartAt).toBe(5000);
    expect(window!.speechEndAt).toBe(7000);
  });

  it('allows multiple endSpeech calls after one beginSpeech', () => {
    session.beginSpeech(1000);
    const w1 = session.endSpeech(2000);
    const w2 = session.endSpeech(3000);
    expect(w1!.speechEndAt).toBe(2000);
    expect(w2!.speechEndAt).toBe(3000);
    expect(w2!.speechStartAt).toBe(1000);
  });

  it('uses Date.now() as default for beginSpeech', () => {
    const before = Date.now();
    session.beginSpeech();
    const after = Date.now();
    const window = session.endSpeech(after + 1000);
    expect(window!.speechStartAt).toBeGreaterThanOrEqual(before);
    expect(window!.speechStartAt).toBeLessThanOrEqual(after);
  });
});
