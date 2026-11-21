import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act, cleanup } from '@testing-library/react';
import { useBrowserTTS } from '../tts/useBrowserTTS';

// The page has ONE speech queue shared by every hook instance (each message row mounts one). The fake queue models
// what Chrome does on it: `cancel()` ends whatever is speaking at once, the interrupted utterance reports its error a
// moment AFTER `cancel()` returned (a replacement may already be handed over by then), and an utterance starts shortly
// after `speak()`.
const INTERRUPTION_REPORT_MS = 1;
const START_MS = 21;
const SPEECH_MS = 400;

class FakeUtterance {
  readonly text: string;
  rate = 1;
  lang = '';
  onstart: (() => void) | null = null;
  onend: (() => void) | null = null;
  onerror: (() => void) | null = null;

  constructor(text: string) {
    this.text = text;
  }
}

class FakeSpeechQueue {
  current: FakeUtterance | null = null;
  private waiting: FakeUtterance[] = [];

  speak(utterance: FakeUtterance) {
    this.waiting.push(utterance);
    this.startNext();
  }

  cancel() {
    const interrupted = this.current;
    this.current = null;
    this.waiting = [];
    if (interrupted) {
      setTimeout(() => interrupted.onerror?.(), INTERRUPTION_REPORT_MS);
    }
  }

  pause() {}

  resume() {}

  private startNext() {
    if (this.current) {
      return;
    }
    const next = this.waiting.shift();
    if (!next) {
      return;
    }
    this.current = next;
    setTimeout(() => {
      if (this.current === next) {
        next.onstart?.();
      }
    }, START_MS);
    setTimeout(() => {
      if (this.current === next) {
        this.current = null;
        next.onend?.();
        this.startNext();
      }
    }, SPEECH_MS);
  }
}

let queue: FakeSpeechQueue;

beforeEach(() => {
  vi.useFakeTimers();
  queue = new FakeSpeechQueue();
  Object.defineProperty(window, 'speechSynthesis', { configurable: true, value: queue });
  vi.stubGlobal('SpeechSynthesisUtterance', FakeUtterance);
});

afterEach(() => {
  // Unmount the rows while the fake queue still exists: their cleanup talks to it.
  cleanup();
  vi.unstubAllGlobals();
  Reflect.deleteProperty(window, 'speechSynthesis');
  vi.useRealTimers();
});

const renderRow = () => renderHook(() => useBrowserTTS());

const advance = (ms: number) =>
  act(() => {
    vi.advanceTimersByTime(ms);
  });

/** A row that has started speaking `text`. */
function speakingRow(text: string) {
  const row = renderRow();
  act(() => row.result.current.speak(text));
  advance(START_MS);
  return row;
}

describe('useBrowserTTS', () => {
  it('plays an utterance and returns to idle when it ends', () => {
    const row = speakingRow('hello');
    expect(row.result.current.state).toBe('playing');

    advance(SPEECH_MS);

    expect(row.result.current.state).toBe('idle');
    expect(queue.current).toBeNull();
  });

  it('returns the interrupted row to idle when another row takes over', () => {
    const first = speakingRow('first row');
    const second = renderRow();

    act(() => second.result.current.speak('second row'));
    advance(START_MS);

    expect(first.result.current.state).toBe('idle');
    expect(second.result.current.state).toBe('playing');
    expect(queue.current?.text).toBe('second row');
  });

  it('keeps playing when the utterance it replaced reports its interruption late', () => {
    const row = speakingRow('first');

    act(() => row.result.current.speak('second'));
    advance(INTERRUPTION_REPORT_MS + 1);
    expect(row.result.current.state).toBe('playing');

    advance(START_MS);
    expect(queue.current?.text).toBe('second');
    expect(row.result.current.state).toBe('playing');
  });

  it('stops its own speech on stop()', () => {
    const row = speakingRow('hello');

    act(() => row.result.current.stop());

    expect(row.result.current.state).toBe('idle');
    expect(queue.current).toBeNull();
  });

  it('stops its own speech when the speaking row unmounts', () => {
    const row = speakingRow('hello');

    row.unmount();

    expect(queue.current).toBeNull();
  });

  describe('a row that is not speaking', () => {
    it('leaves another row speaking when it unmounts', () => {
      const speaker = speakingRow('first row');
      const bystander = renderRow();

      bystander.unmount();
      advance(INTERRUPTION_REPORT_MS + 1);

      expect(speaker.result.current.state).toBe('playing');
      expect(queue.current?.text).toBe('first row');
    });

    it('leaves another row speaking when it is stopped', () => {
      const speaker = speakingRow('first row');
      const bystander = renderRow();

      act(() => bystander.result.current.stop());
      advance(INTERRUPTION_REPORT_MS + 1);

      expect(speaker.result.current.state).toBe('playing');
      expect(queue.current?.text).toBe('first row');
    });

    it('leaves another row speaking when its own text has nothing to speak', () => {
      const speaker = speakingRow('first row');
      const bystander = renderRow();

      act(() => bystander.result.current.speak(''));
      advance(INTERRUPTION_REPORT_MS + 1);

      expect(speaker.result.current.state).toBe('playing');
      expect(queue.current?.text).toBe('first row');
    });
  });
});
