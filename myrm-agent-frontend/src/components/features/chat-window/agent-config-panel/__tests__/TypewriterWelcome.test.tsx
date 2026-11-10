import { act, render } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { startFakeClock, stopFakeClock } from '@/test-utils/fakeClock';

import TypewriterWelcome from '../TypewriterWelcome';

const TYPING_MS = 10;
const DWELL_MS = 100;
const FADE_MS = 400;

const elapse = (ms: number) => act(() => vi.advanceTimersByTime(ms));

type LineProps = Partial<Parameters<typeof TypewriterWelcome>[0]>;

function line(overrides: LineProps = {}) {
  const props = { text: 'Hi!', show: true, typingSpeed: TYPING_MS, displayDuration: DWELL_MS, ...overrides };
  const view = render(<TypewriterWelcome {...props} />);
  return {
    ...view,
    update: (next: LineProps) => view.rerender(<TypewriterWelcome {...props} {...next} />),
    shown: () => view.container.querySelector('p')?.textContent ?? null,
    cursor: () => view.container.querySelector('.animate-pulse'),
    isFading: () => view.container.firstElementChild?.classList.contains('opacity-0') ?? false,
  };
}

beforeEach(startFakeClock);
afterEach(stopFakeClock);

describe('TypewriterWelcome typing', () => {
  it('shows nothing until it is asked to', () => {
    const { container } = line({ show: false });

    expect(container).toBeEmptyDOMElement();
  });

  it('starts with an empty line and a cursor, then adds one character per typing step', () => {
    const view = line();

    expect(view.shown()).toBe('');
    expect(view.cursor()).not.toBeNull();

    elapse(TYPING_MS);
    expect(view.shown()).toBe('H');
    elapse(TYPING_MS);
    expect(view.shown()).toBe('Hi');
    elapse(TYPING_MS - 1);
    expect(view.shown()).toBe('Hi');
    elapse(1);
    expect(view.shown()).toBe('Hi!');
  });

  it('keeps the cursor for one more step after the last character, then drops it', () => {
    const view = line();

    elapse(TYPING_MS * 3);
    expect(view.shown()).toBe('Hi!');
    expect(view.cursor()).not.toBeNull();

    elapse(TYPING_MS);
    expect(view.shown()).toBe('Hi!');
    expect(view.cursor()).toBeNull();
  });

  it('uses the given typing speed', () => {
    const view = line({ typingSpeed: 50 });

    elapse(49);
    expect(view.shown()).toBe('');
    elapse(1);
    expect(view.shown()).toBe('H');
    elapse(49);
    expect(view.shown()).toBe('H');
    elapse(1);
    expect(view.shown()).toBe('Hi');
  });

  it('shows an empty line for an empty text and drops the cursor after the first step', () => {
    const view = line({ text: '' });

    elapse(TYPING_MS);

    expect(view.shown()).toBe('');
    expect(view.cursor()).toBeNull();
  });
});

describe('TypewriterWelcome leaving', () => {
  it('stays for the display duration after typing, then fades, then completes once', () => {
    const onComplete = vi.fn<() => void>();
    const view = line({ onComplete });

    elapse(TYPING_MS * 4 + DWELL_MS - 1);
    expect(view.isFading()).toBe(false);
    elapse(1);
    expect(view.isFading()).toBe(true);
    expect(view.shown()).toBe('Hi!');
    expect(onComplete).not.toHaveBeenCalled();

    elapse(FADE_MS - 1);
    expect(view.shown()).toBe('Hi!');
    expect(onComplete).not.toHaveBeenCalled();
    elapse(1);

    expect(view.container).toBeEmptyDOMElement();
    expect(onComplete).toHaveBeenCalledTimes(1);
    elapse(10_000);
    expect(onComplete).toHaveBeenCalledTimes(1);
  });

  it('uses the given display duration', () => {
    const view = line({ displayDuration: 250 });

    elapse(TYPING_MS * 4 + 249);
    expect(view.isFading()).toBe(false);
    elapse(1);

    expect(view.isFading()).toBe(true);
  });

  it('hides itself after the fade even when nobody reacts to the completion', () => {
    const view = line();

    elapse(TYPING_MS * 4 + DWELL_MS + FADE_MS);

    expect(view.container).toBeEmptyDOMElement();
  });

  it('leaves at once, without completing, when it is switched off while typing', () => {
    const onComplete = vi.fn<() => void>();
    const view = line({ onComplete });
    elapse(TYPING_MS);

    view.update({ show: false });

    expect(view.container).toBeEmptyDOMElement();
    elapse(10_000);
    expect(onComplete).not.toHaveBeenCalled();
  });

  it('leaves at once, without completing, when it is switched off while it waits or fades', () => {
    const onComplete = vi.fn<() => void>();
    const view = line({ onComplete });
    elapse(TYPING_MS * 4 + DWELL_MS / 2);
    view.update({ show: false });
    elapse(10_000);

    expect(view.container).toBeEmptyDOMElement();
    expect(onComplete).not.toHaveBeenCalled();

    view.update({ show: true });
    elapse(TYPING_MS * 4 + DWELL_MS + 1);
    view.update({ show: false });
    elapse(10_000);

    expect(onComplete).not.toHaveBeenCalled();
  });

  it('does not complete after it was removed', () => {
    const onComplete = vi.fn<() => void>();
    const view = line({ onComplete });
    elapse(TYPING_MS * 4 + DWELL_MS + 1);

    view.unmount();
    elapse(10_000);

    expect(onComplete).not.toHaveBeenCalled();
    expect(vi.getTimerCount()).toBe(0);
  });
});

describe('TypewriterWelcome starting again', () => {
  it('types from the beginning each time it is switched on', () => {
    const view = line();
    elapse(TYPING_MS * 2);
    view.update({ show: false });

    view.update({ show: true });
    expect(view.shown()).toBe('');
    elapse(TYPING_MS);

    expect(view.shown()).toBe('H');
  });

  it('starts over when the text changes', () => {
    const view = line();
    elapse(TYPING_MS * 3);
    expect(view.shown()).toBe('Hi!');

    view.update({ text: 'Hey' });
    expect(view.shown()).toBe('');
    elapse(TYPING_MS * 2);

    expect(view.shown()).toBe('He');
  });

  it('starts over when the timing changes', () => {
    const view = line();
    elapse(TYPING_MS * 2);

    view.update({ typingSpeed: 20 });
    expect(view.shown()).toBe('');
    elapse(20);

    expect(view.shown()).toBe('H');
  });

  it('keeps typing when the parent only hands in another completion callback', () => {
    const first = vi.fn<() => void>();
    const second = vi.fn<() => void>();
    const view = line({ onComplete: first });
    elapse(TYPING_MS * 2);

    view.update({ onComplete: second });
    expect(view.shown()).toBe('Hi');
    elapse(TYPING_MS * 2 + DWELL_MS + FADE_MS);

    expect(first).not.toHaveBeenCalled();
    expect(second).toHaveBeenCalledTimes(1);
  });
});
