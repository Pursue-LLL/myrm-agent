import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import {
  StreamBackpressureController,
} from '../streamBackpressureController';

describe('StreamBackpressureController', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.useRealTimers();
  });

  it('buffers high-frequency chunks and flushes combined delta synchronously', () => {
    const renderCallback = vi.fn();
    const controller = new StreamBackpressureController(renderCallback, {
      targetFps: 60,
      maxBufferedChars: 500,
      useTimerFallback: true,
    });

    controller.pushChunk('Hello ');
    controller.pushChunk('World! ');
    controller.pushChunk('This is a test.');

    // Before flush, callback has not been executed yet
    expect(renderCallback).not.toHaveBeenCalled();

    // Trigger flushSync
    controller.flushSync();

    expect(renderCallback).toHaveBeenCalledTimes(1);
    expect(renderCallback).toHaveBeenCalledWith('Hello World! This is a test.');

    const metrics = controller.getMetrics();
    expect(metrics.totalChunksPushed).toBe(3);
    expect(metrics.totalFramesRendered).toBe(1);
    expect(metrics.totalMergedChunks).toBe(2);
    expect(metrics.emergencyFlushes).toBe(0);

    controller.destroy();
  });

  it('triggers emergency flush when buffer exceeds maxBufferedChars limit', () => {
    const renderCallback = vi.fn();
    const controller = new StreamBackpressureController(renderCallback, {
      maxBufferedChars: 50,
      useTimerFallback: true,
    });

    // Pushing small chunk under threshold
    controller.pushChunk('Short chunk 1. ');
    expect(renderCallback).not.toHaveBeenCalled();

    // Pushing heavy chunk causing buffer to cross 50 chars threshold
    const massiveChunk = 'A'.repeat(60);
    controller.pushChunk(massiveChunk);

    // Emergency flush triggers immediately without waiting for RAF/timer
    expect(renderCallback).toHaveBeenCalledTimes(1);
    expect(renderCallback).toHaveBeenCalledWith(`Short chunk 1. ${massiveChunk}`);

    const metrics = controller.getMetrics();
    expect(metrics.emergencyFlushes).toBe(1);
    expect(metrics.totalFramesRendered).toBe(1);

    controller.destroy();
  });

  it('automatically flushes remaining buffer on endStream', () => {
    const renderCallback = vi.fn();
    const controller = new StreamBackpressureController(renderCallback, {
      useTimerFallback: true,
    });

    controller.pushChunk('Final message segment.');
    expect(renderCallback).not.toHaveBeenCalled();

    controller.endStream();

    expect(renderCallback).toHaveBeenCalledTimes(1);
    expect(renderCallback).toHaveBeenCalledWith('Final message segment.');

    controller.destroy();
  });

  it('flushes via timer fallback when time elapses', () => {
    const renderCallback = vi.fn();
    const controller = new StreamBackpressureController(renderCallback, {
      targetFps: 60,
      useTimerFallback: true,
    });

    controller.pushChunk('Timer triggered chunk.');
    expect(renderCallback).not.toHaveBeenCalled();

    // Fast-forward timer by 20ms (> 16ms frame)
    vi.advanceTimersByTime(25);

    expect(renderCallback).toHaveBeenCalledTimes(1);
    expect(renderCallback).toHaveBeenCalledWith('Timer triggered chunk.');

    controller.destroy();
  });

  it('ignores chunks after destroy is called', () => {
    const renderCallback = vi.fn();
    const controller = new StreamBackpressureController(renderCallback);

    controller.destroy();
    controller.pushChunk('Should be ignored');
    controller.flushSync();

    expect(renderCallback).not.toHaveBeenCalled();
    expect(controller.getMetrics().totalChunksPushed).toBe(0);
  });
});
