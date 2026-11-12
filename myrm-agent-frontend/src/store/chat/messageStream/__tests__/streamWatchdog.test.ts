import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { createStreamWatchdog, USAGE_GRACE_MS } from '../streamWatchdog';

function createActions() {
  return {
    setLoading: vi.fn(),
    clearActiveStream: vi.fn(),
    setMessageAppeared: vi.fn(),
    scheduleAutoSave: vi.fn(),
  };
}

describe('createStreamWatchdog', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.spyOn(console, 'warn').mockImplementation(() => undefined);
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it('heals the turn when the reader reaches EOF without a terminal event', () => {
    const actions = createActions();
    const watchdog = createStreamWatchdog({ actions });

    watchdog.onReaderDone();

    expect(actions.setLoading).toHaveBeenCalledWith(false);
    expect(actions.clearActiveStream).toHaveBeenCalledTimes(1);
    expect(actions.setMessageAppeared).toHaveBeenCalledWith(true);
    expect(actions.scheduleAutoSave).toHaveBeenCalledTimes(1);
    expect(console.warn).toHaveBeenCalledWith(expect.stringContaining('reader reached EOF without terminal event'));
    watchdog.dispose();
  });

  it('does not heal on EOF once the terminal event was received', () => {
    const actions = createActions();
    const watchdog = createStreamWatchdog({ actions });

    watchdog.markTerminalReceived();
    watchdog.onReaderDone();

    expect(actions.setLoading).not.toHaveBeenCalled();
    watchdog.dispose();
  });

  it('heals when a usage chunk is not followed by a terminal event within the grace period', () => {
    const actions = createActions();
    const watchdog = createStreamWatchdog({ actions });

    watchdog.notifyUsageReceived();
    vi.advanceTimersByTime(USAGE_GRACE_MS - 1);
    expect(actions.setLoading).not.toHaveBeenCalled();

    vi.advanceTimersByTime(1);
    expect(actions.setLoading).toHaveBeenCalledWith(false);
    expect(actions.clearActiveStream).toHaveBeenCalledTimes(1);
    expect(console.warn).toHaveBeenCalledWith(expect.stringContaining('usage received without terminal event'));
    watchdog.dispose();
  });

  it('lets a terminal event inside the usage grace period cancel the heal', () => {
    const actions = createActions();
    const watchdog = createStreamWatchdog({ actions });

    watchdog.notifyUsageReceived();
    vi.advanceTimersByTime(USAGE_GRACE_MS - 1);
    watchdog.markTerminalReceived();

    expect(vi.getTimerCount()).toBe(0);
    vi.advanceTimersByTime(2 * USAGE_GRACE_MS);
    expect(actions.setLoading).not.toHaveBeenCalled();
    watchdog.dispose();
  });

  it('heals at most once, whichever signal comes second', () => {
    const actions = createActions();
    const watchdog = createStreamWatchdog({ actions });

    watchdog.notifyUsageReceived();
    vi.advanceTimersByTime(USAGE_GRACE_MS);
    watchdog.onReaderDone();
    watchdog.notifyUsageReceived();
    vi.advanceTimersByTime(2 * USAGE_GRACE_MS);

    expect(actions.setLoading).toHaveBeenCalledTimes(1);
    watchdog.dispose();
  });

  it('leaves nothing pending once disposed', () => {
    const actions = createActions();
    const watchdog = createStreamWatchdog({ actions });

    watchdog.notifyUsageReceived();
    watchdog.dispose();

    expect(vi.getTimerCount()).toBe(0);
    vi.advanceTimersByTime(2 * USAGE_GRACE_MS);
    expect(actions.setLoading).not.toHaveBeenCalled();
  });
});
