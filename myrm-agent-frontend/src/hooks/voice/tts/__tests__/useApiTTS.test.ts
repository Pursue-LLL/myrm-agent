import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act, cleanup } from '@testing-library/react';
import { useApiTTS } from '../useApiTTS';

const toastError = vi.hoisted(() => vi.fn());

vi.mock('@/lib/api', () => ({ getApiUrl: (path: string) => path }));
vi.mock('@/lib/utils/toast', () => ({ toast: { error: toastError } }));

// Every message row mounts its own engine instance and audio elements play independently of each other, so nothing
// but the engine keeps two rows audible at once. The fakes model that: each synthesis answers at once unless the test
// holds it back, and every audio element stays audible until the engine pauses it or the test lets it end. jsdom has
// no MediaSource, so the engine takes its one-shot synthesis path.
class FakeAudio {
  static instances: FakeAudio[] = [];
  paused = true;
  onplay: (() => void) | null = null;
  onended: (() => void) | null = null;

  constructor() {
    FakeAudio.instances.push(this);
  }

  play() {
    this.paused = false;
    this.onplay?.();
    return Promise.resolve();
  }

  pause() {
    this.paused = true;
  }

  removeAttribute() {}

  load() {}
}

interface HeldRequest {
  signal: AbortSignal;
  answer: () => void;
}

const held = new Map<string, HeldRequest>();

/** Synthesis requests for the texts in `heldTexts` stay pending until the test answers them; the rest answer at once. */
function stubSynthesis(heldTexts: string[] = []) {
  vi.stubGlobal(
    'fetch',
    vi.fn((_url: string, init: RequestInit) => {
      const { text } = JSON.parse(String(init.body)) as { text: string };
      const signal = init.signal as AbortSignal;
      return new Promise((resolve, reject) => {
        const answer = () => resolve({ ok: true, status: 200, blob: () => Promise.resolve(new Blob(['audio'])) });
        signal.addEventListener('abort', () => reject(new DOMException('aborted', 'AbortError')));
        if (heldTexts.includes(text)) {
          held.set(text, { signal, answer });
        } else {
          answer();
        }
      });
    }),
  );
}

beforeEach(() => {
  FakeAudio.instances = [];
  held.clear();
  toastError.mockClear();
  vi.stubGlobal('Audio', FakeAudio);
  Object.defineProperty(URL, 'createObjectURL', { configurable: true, writable: true, value: () => 'blob:tts' });
  Object.defineProperty(URL, 'revokeObjectURL', { configurable: true, writable: true, value: () => undefined });
});

afterEach(() => {
  // Unmount the rows while the fakes still exist: their cleanup talks to them.
  cleanup();
  vi.unstubAllGlobals();
  Reflect.deleteProperty(URL, 'createObjectURL');
  Reflect.deleteProperty(URL, 'revokeObjectURL');
});

const renderRow = () => renderHook(() => useApiTTS({ provider: 'edge' }));
type Row = ReturnType<typeof renderRow>;

const audible = () => FakeAudio.instances.filter((audio) => !audio.paused).length;

/** Lets the synthesis chain (fetch, blob, play) run through every step that does not wait on the network. */
const settle = () =>
  act(async () => {
    await new Promise<void>((resolve) => setTimeout(resolve, 0));
  });

async function speak(row: Row, text: string) {
  act(() => {
    row.result.current.speak(text);
  });
  await settle();
}

/** The audio plays to its last sample on its own, the way a real element ends without anyone stopping it. */
function endNaturally(audio: FakeAudio) {
  act(() => {
    audio.paused = true;
    audio.onended?.();
  });
}

describe('useApiTTS', () => {
  it('stops the row that is playing when another row starts speaking', async () => {
    stubSynthesis();
    const first = renderRow();
    const second = renderRow();

    await speak(first, 'first row');
    await speak(second, 'second row');

    expect(audible()).toBe(1);
    expect(first.result.current.state).toBe('idle');
    expect(second.result.current.state).toBe('playing');
  });

  it('aborts the request of a row that is still loading when another row takes over', async () => {
    stubSynthesis(['first row']);
    const first = renderRow();
    const second = renderRow();

    await speak(first, 'first row');
    expect(first.result.current.state).toBe('loading');
    await speak(second, 'second row');

    const request = held.get('first row');
    expect(request?.signal.aborted).toBe(true);
    expect(first.result.current.state).toBe('idle');
    expect(second.result.current.state).toBe('playing');

    // A late answer from the superseded request must not start a second audio.
    await act(async () => {
      request?.answer();
      await new Promise<void>((resolve) => setTimeout(resolve, 0));
    });
    expect(audible()).toBe(1);
    expect(toastError).not.toHaveBeenCalled();
  });

  it('keeps a single audio when the same row speaks again', async () => {
    stubSynthesis();
    const row = renderRow();

    await speak(row, 'first');
    await speak(row, 'second');

    expect(audible()).toBe(1);
    expect(row.result.current.state).toBe('playing');
  });

  it('leaves the playing row alone when another row has nothing to read', async () => {
    stubSynthesis();
    const speaker = renderRow();
    const bystander = renderRow();

    await speak(speaker, 'first row');
    await speak(bystander, '```ts\nconst unreadable = true;\n```');

    expect(audible()).toBe(1);
    expect(speaker.result.current.state).toBe('playing');
  });

  it('lets a row that was taken over take the audio back', async () => {
    stubSynthesis();
    const first = renderRow();
    const second = renderRow();

    await speak(first, 'first row');
    await speak(second, 'second row');
    await speak(first, 'first row again');

    expect(audible()).toBe(1);
    expect(first.result.current.state).toBe('playing');
    expect(second.result.current.state).toBe('idle');
  });

  it('still stops the speaking row after a row it replaced has unmounted', async () => {
    stubSynthesis();
    const first = renderRow();
    const second = renderRow();
    const third = renderRow();

    await speak(first, 'first row');
    await speak(second, 'second row');
    first.unmount();
    await speak(third, 'third row');

    expect(audible()).toBe(1);
    expect(second.result.current.state).toBe('idle');
    expect(third.result.current.state).toBe('playing');
  });

  it('lets another row speak after the speaking row has finished on its own', async () => {
    stubSynthesis();
    const first = renderRow();
    const second = renderRow();

    await speak(first, 'first row');
    endNaturally(FakeAudio.instances[0]);
    expect(first.result.current.state).toBe('idle');
    await speak(second, 'second row');

    expect(audible()).toBe(1);
    expect(first.result.current.state).toBe('idle');
    expect(second.result.current.state).toBe('playing');
    expect(toastError).not.toHaveBeenCalled();
  });
});
