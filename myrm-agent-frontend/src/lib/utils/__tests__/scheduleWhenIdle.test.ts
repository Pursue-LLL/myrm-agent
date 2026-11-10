/**
 * Low-priority startup work: it waits for an idle browser, or a moment where idle callbacks do not exist (the macOS
 * desktop shell), and a caller that goes away first can take its work back.
 */
import { afterEach, describe, expect, it, vi } from 'vitest';

import { expectDefined } from '@/test-utils/expectDefined';

import { scheduleWhenIdle } from '../scheduleWhenIdle';

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

/** A shell without idle callbacks, with timers under test control. */
function useShellWithoutIdleCallbacks(): void {
  vi.useFakeTimers();
  // Stubbed after the fake clock, which would otherwise bring idle callbacks of its own.
  vi.stubGlobal('requestIdleCallback', undefined);
}

describe('scheduleWhenIdle: browsers with idle callbacks', () => {
  function stubIdleCallbacks() {
    let idle: (() => void) | undefined;
    const request = vi.fn((callback: () => void) => {
      idle = callback;
      return 7;
    });
    const cancel = vi.fn<(handle: number) => void>();
    vi.stubGlobal('requestIdleCallback', request);
    vi.stubGlobal('cancelIdleCallback', cancel);
    return {
      cancel,
      goIdle: () => {
        expectDefined(idle, 'idle callback');
        idle();
      },
    };
  }

  it('runs the task once the browser goes idle, not before', () => {
    const { goIdle } = stubIdleCallbacks();
    const task = vi.fn();

    scheduleWhenIdle(task);
    expect(task).not.toHaveBeenCalled();

    goIdle();
    expect(task).toHaveBeenCalledOnce();
  });

  it('takes the idle callback back by its handle', () => {
    const { cancel } = stubIdleCallbacks();

    scheduleWhenIdle(vi.fn())();

    expect(cancel).toHaveBeenCalledExactlyOnceWith(7);
  });
});

describe('scheduleWhenIdle: shells without idle callbacks', () => {
  it('runs the task after a short timer, not at once', () => {
    useShellWithoutIdleCallbacks();
    const task = vi.fn();

    scheduleWhenIdle(task);
    expect(task).not.toHaveBeenCalled();
    vi.advanceTimersByTime(0);
    expect(task).not.toHaveBeenCalled();

    vi.advanceTimersByTime(1);
    expect(task).toHaveBeenCalledOnce();
  });

  it('never runs a task that was taken back', () => {
    useShellWithoutIdleCallbacks();
    const task = vi.fn();

    scheduleWhenIdle(task)();
    vi.advanceTimersByTime(1000);

    expect(task).not.toHaveBeenCalled();
  });
});
