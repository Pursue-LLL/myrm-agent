import { afterEach, beforeEach, describe, it, expect, vi } from 'vitest';
import { isImeComposing, IME_CONFIRM_KEY_WINDOW_MS } from '../imeUtils';

type ImeEventLike = {
  key?: string;
  keyCode?: number;
  isComposing?: boolean;
  nativeEvent?: {
    isComposing?: boolean;
  };
};

describe('imeUtils - isImeComposing', () => {
  it('returns true when nativeEvent.isComposing is true', () => {
    const event: ImeEventLike = { nativeEvent: { isComposing: true } };
    expect(isImeComposing(event as unknown as React.KeyboardEvent)).toBe(true);
  });

  it('returns true when event.isComposing is true', () => {
    const event: ImeEventLike = { isComposing: true };
    expect(isImeComposing(event as unknown as React.KeyboardEvent)).toBe(true);
  });

  it('returns true when event.key is Process', () => {
    const event: ImeEventLike = { key: 'Process', isComposing: false };
    expect(isImeComposing(event as unknown as React.KeyboardEvent)).toBe(true);
  });

  it('returns true when event.keyCode is 229', () => {
    const event: ImeEventLike = { keyCode: 229, isComposing: false };
    expect(isImeComposing(event as unknown as React.KeyboardEvent)).toBe(true);
  });

  it('returns false for normal Enter press without IME composition', () => {
    const event: ImeEventLike = {
      key: 'Enter',
      keyCode: 13,
      isComposing: false,
      nativeEvent: { isComposing: false },
    };
    expect(isImeComposing(event as unknown as React.KeyboardEvent)).toBe(false);
  });
});

/**
 * Safari ends the composition first and sends the confirming key afterwards as a plain keydown. Whether that key
 * belongs to the composition is decided by when the browser created the two events, not by when the page got around to
 * handling them: a busy main thread must not turn an input method's Enter into a "send".
 */
describe('imeUtils - the confirm key Safari sends after compositionend', () => {
  /** Each test starts long after the confirm window of the previous one has closed. */
  let clock = Date.parse('2026-10-17T00:00:00Z');

  beforeEach(() => {
    clock += 10_000;
    vi.useFakeTimers({ toFake: ['Date'] });
    vi.setSystemTime(clock);
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  /** A real keydown created `msAfterCompositionEnd` after the composition ended (negative: before it). */
  function keydownCreated(msAfterCompositionEnd: number, init: KeyboardEventInit): KeyboardEvent {
    vi.setSystemTime(clock + msAfterCompositionEnd);
    return new KeyboardEvent('keydown', { isComposing: false, ...init });
  }

  function endComposition(): void {
    vi.setSystemTime(clock);
    document.dispatchEvent(new Event('compositionend'));
  }

  const plainEnter: KeyboardEventInit = { key: 'Enter', keyCode: 13 };

  it('swallows the Enter that arrives right after compositionend', () => {
    endComposition();

    expect(isImeComposing(keydownCreated(5, plainEnter))).toBe(true);
  });

  it('swallows the Escape that cancels a composition right after compositionend', () => {
    endComposition();

    expect(isImeComposing(keydownCreated(5, { key: 'Escape', keyCode: 27 }))).toBe(true);
  });

  it('releases the guard once the confirm window has elapsed', () => {
    endComposition();

    expect(isImeComposing(keydownCreated(IME_CONFIRM_KEY_WINDOW_MS - 1, plainEnter))).toBe(true);
    expect(isImeComposing(keydownCreated(IME_CONFIRM_KEY_WINDOW_MS, plainEnter))).toBe(false);
  });

  it('never swallows keys other than Enter and Escape inside the confirm window', () => {
    endComposition();

    expect(isImeComposing(keydownCreated(5, { key: 'ArrowUp', keyCode: 38 }))).toBe(false);
  });

  it('still swallows the confirm key when the page handles it long after the browser created it', () => {
    endComposition();
    const confirm = keydownCreated(30, plainEnter);

    vi.setSystemTime(clock + 30 + 5 * IME_CONFIRM_KEY_WINDOW_MS);

    expect(isImeComposing(confirm)).toBe(true);
  });

  it('swallows the confirm key whichever of the two events the browser stamped first, within the window', () => {
    endComposition();

    expect(isImeComposing(keydownCreated(-5, plainEnter))).toBe(true);
    expect(isImeComposing(keydownCreated(-5 * IME_CONFIRM_KEY_WINDOW_MS, plainEnter))).toBe(false);
  });

  it('cannot place an event without a timestamp next to the composition, so it does not swallow it', () => {
    endComposition();

    expect(isImeComposing({ key: 'Enter', keyCode: 13, isComposing: false })).toBe(false);
  });
});
