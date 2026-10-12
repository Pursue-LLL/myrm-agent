import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { createStreamWatchdog } from '../streamWatchdog';

describe('createStreamWatchdog', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('does nothing when terminal event is received normally within threshold', () => {
    const setLoading = vi.fn();
    const clearActiveStream = vi.fn();
    const setMessageAppeared = vi.fn();
    const onHeal = vi.fn();

    const watchdog = createStreamWatchdog({
      silenceTimeoutMs: 3000,
      usageGraceMs: 1000,
      onHeal,
      getState: () => ({
        loading: true,
        messages: [{ role: 'assistant', content: 'hello' }],
      }),
      actions: {
        setLoading,
        clearActiveStream,
        setMessageAppeared,
      },
    });

    watchdog.feed('message_chunk');
    vi.advanceTimersByTime(1500);

    watchdog.markTerminalReceived();
    vi.advanceTimersByTime(5000);

    expect(watchdog.isTerminalReceived()).toBe(true);
    expect(watchdog.isHealed()).toBe(false);
    expect(setLoading).not.toHaveBeenCalled();
    expect(clearActiveStream).not.toHaveBeenCalled();
    expect(onHeal).not.toHaveBeenCalled();
    watchdog.dispose();
  });

  it('triggers self-healing on prolonged silence when terminal event is missing', () => {
    const setLoading = vi.fn();
    const clearActiveStream = vi.fn();
    const setMessageAppeared = vi.fn();
    const _processSuggestions = vi.fn();
    const onHeal = vi.fn();

    const mockMsg = { role: 'assistant', content: 'chunk response' };
    const watchdog = createStreamWatchdog({
      silenceTimeoutMs: 3000,
      usageGraceMs: 1000,
      onHeal,
      getState: () => ({
        loading: true,
        messages: [mockMsg],
      }),
      actions: {
        setLoading,
        clearActiveStream,
        setMessageAppeared,
        _processSuggestions,
      },
    });

    watchdog.feed('message_chunk');
    vi.advanceTimersByTime(1000);

    // Feed another chunk, extending silence window
    watchdog.feed('message_chunk');
    vi.advanceTimersByTime(2000);
    expect(setLoading).not.toHaveBeenCalled();

    // Now silence reaches 3000ms threshold
    vi.advanceTimersByTime(1001);

    expect(watchdog.isHealed()).toBe(true);
    expect(setLoading).toHaveBeenCalledWith(false);
    expect(clearActiveStream).toHaveBeenCalled();
    expect(setMessageAppeared).toHaveBeenCalledWith(true);
    expect(_processSuggestions).toHaveBeenCalledWith(mockMsg);
    expect(onHeal).toHaveBeenCalledWith(expect.stringContaining('silence timeout'));
    watchdog.dispose();
  });

  it('triggers self-healing on usage event grace period when terminal event is dropped', () => {
    const setLoading = vi.fn();
    const clearActiveStream = vi.fn();
    const setMessageAppeared = vi.fn();
    const onHeal = vi.fn();

    const watchdog = createStreamWatchdog({
      silenceTimeoutMs: 4000,
      usageGraceMs: 1200,
      onHeal,
      getState: () => ({
        loading: true,
        messages: [{ role: 'assistant', content: 'finished task' }],
      }),
      actions: {
        setLoading,
        clearActiveStream,
        setMessageAppeared,
      },
    });

    watchdog.feed('message_chunk');
    watchdog.notifyUsageReceived();

    // Before grace period expires
    vi.advanceTimersByTime(1000);
    expect(setLoading).not.toHaveBeenCalled();
    expect(watchdog.isHealed()).toBe(false);

    // Once usage grace period expires
    vi.advanceTimersByTime(201);
    expect(watchdog.isHealed()).toBe(true);
    expect(setLoading).toHaveBeenCalledWith(false);
    expect(clearActiveStream).toHaveBeenCalled();
    expect(onHeal).toHaveBeenCalledWith(expect.stringContaining('usage received without terminal event'));
    watchdog.dispose();
  });

  it('immediately triggers self-healing when reader reaches EOF without terminal event', () => {
    const setLoading = vi.fn();
    const clearActiveStream = vi.fn();
    const setMessageAppeared = vi.fn();
    const onHeal = vi.fn();

    const watchdog = createStreamWatchdog({
      silenceTimeoutMs: 5000,
      onHeal,
      getState: () => ({
        loading: true,
        messages: [{ role: 'assistant', content: 'abrupt EOF' }],
      }),
      actions: {
        setLoading,
        clearActiveStream,
        setMessageAppeared,
      },
    });

    watchdog.feed('message_chunk');
    expect(watchdog.isHealed()).toBe(false);

    // Reader done before silence timeout
    watchdog.onReaderDone();

    expect(watchdog.isHealed()).toBe(true);
    expect(setLoading).toHaveBeenCalledWith(false);
    expect(clearActiveStream).toHaveBeenCalled();
    expect(onHeal).toHaveBeenCalledWith(expect.stringContaining('reader reached EOF without terminal event'));
    watchdog.dispose();
  });

  it('does not trigger self-healing on reader EOF if terminal event was already received', () => {
    const setLoading = vi.fn();
    const onHeal = vi.fn();

    const watchdog = createStreamWatchdog({
      onHeal,
      getState: () => ({
        loading: false,
        messages: [],
      }),
      actions: {
        setLoading,
      },
    });

    watchdog.feed('message_chunk');
    watchdog.markTerminalReceived();
    watchdog.onReaderDone();

    expect(watchdog.isHealed()).toBe(false);
    expect(setLoading).not.toHaveBeenCalled();
    expect(onHeal).not.toHaveBeenCalled();
    watchdog.dispose();
  });

  it('dispose clears timers and prevents subsequent healing', () => {
    const setLoading = vi.fn();
    const onHeal = vi.fn();

    const watchdog = createStreamWatchdog({
      silenceTimeoutMs: 2000,
      onHeal,
      getState: () => ({
        loading: true,
        messages: [],
      }),
      actions: {
        setLoading,
      },
    });

    watchdog.feed('message_chunk');
    watchdog.dispose();

    vi.advanceTimersByTime(5000);
    expect(watchdog.isHealed()).toBe(false);
    expect(setLoading).not.toHaveBeenCalled();
  });
});
