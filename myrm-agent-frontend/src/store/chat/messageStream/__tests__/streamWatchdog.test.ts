import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { createStreamWatchdog, STREAM_SILENCE_TIMEOUT_MS } from '../streamWatchdog';

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
    const onHeal = vi.fn();

    const watchdog = createStreamWatchdog({
      silenceTimeoutMs: 3000,
      usageGraceMs: 1000,
      onHeal,
      actions: {
        setLoading,
        clearActiveStream,
        setMessageAppeared,
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

  describe('transport liveness', () => {
    // The server's stream buffer sends a heartbeat after this much idle time (`heartbeat_interval`).
    const SERVER_HEARTBEAT_INTERVAL_MS = 15_000;

    it('tolerates three missed server heartbeats before it heals a silent stream', () => {
      const setLoading = vi.fn();
      const onHeal = vi.fn();
      const watchdog = createStreamWatchdog({ onHeal, actions: { setLoading } });

      watchdog.feed('tasks_steps');
      vi.advanceTimersByTime(3 * SERVER_HEARTBEAT_INTERVAL_MS - 1);
      expect(setLoading).not.toHaveBeenCalled();

      vi.advanceTimersByTime(1);
      expect(setLoading).toHaveBeenCalledWith(false);
      expect(onHeal).toHaveBeenCalledWith(expect.stringContaining('silence timeout'));
      watchdog.dispose();
    });

    it('postpones the heal with every heartbeat of a stream that already delivered data', () => {
      const setLoading = vi.fn();
      const watchdog = createStreamWatchdog({ actions: { setLoading } });

      watchdog.feed('tasks_steps');
      for (let beat = 0; beat < 3; beat += 1) {
        vi.advanceTimersByTime(STREAM_SILENCE_TIMEOUT_MS - 1);
        watchdog.keepAlive();
      }
      expect(setLoading).not.toHaveBeenCalled();

      vi.advanceTimersByTime(STREAM_SILENCE_TIMEOUT_MS);
      expect(setLoading).toHaveBeenCalledWith(false);
      watchdog.dispose();
    });

    it('does not start watching a stream that has delivered no business event yet', () => {
      const setLoading = vi.fn();
      const watchdog = createStreamWatchdog({ actions: { setLoading } });

      watchdog.keepAlive();
      vi.advanceTimersByTime(2 * STREAM_SILENCE_TIMEOUT_MS);

      expect(setLoading).not.toHaveBeenCalled();
      watchdog.dispose();
    });

    it('lets a heartbeat neither revive a finished turn nor re-arm a healed one', () => {
      const finishedLoading = vi.fn();
      const finished = createStreamWatchdog({ actions: { setLoading: finishedLoading } });
      finished.feed('message_chunk');
      finished.markTerminalReceived();
      finished.keepAlive();
      vi.advanceTimersByTime(2 * STREAM_SILENCE_TIMEOUT_MS);
      expect(finishedLoading).not.toHaveBeenCalled();
      finished.dispose();

      const healedLoading = vi.fn();
      const healed = createStreamWatchdog({ actions: { setLoading: healedLoading } });
      healed.feed('message_chunk');
      vi.advanceTimersByTime(STREAM_SILENCE_TIMEOUT_MS);
      healed.keepAlive();
      vi.advanceTimersByTime(2 * STREAM_SILENCE_TIMEOUT_MS);
      expect(healedLoading).toHaveBeenCalledTimes(1);
      healed.dispose();
    });
  });
});
