import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import {
  calculateAgentCost,
  formatTokenCount,
  formatCostUsd,
  createThrottledSnapshotEngine,
} from '../chatSnapshotThrottleEngine';

describe('chatSnapshotThrottleEngine', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('calculates agent cost accurately based on rates', () => {
    const rate = { prompt: 0.0015, completion: 0.002 };
    // prompt: (20000 / 1000) * 0.0015 = 0.03
    // completion: (5000 / 1000) * 0.002 = 0.01
    // total = 0.04
    const cost = calculateAgentCost(20000, 5000, rate);
    expect(cost).toBe(0.04);
  });

  it('formats token count correctly', () => {
    expect(formatTokenCount(850)).toBe('850');
    expect(formatTokenCount(32400)).toBe('32.4k');
    expect(formatTokenCount(1500000)).toBe('1.5M');
  });

  it('formats USD cost values correctly', () => {
    expect(formatCostUsd(0)).toBe('$0.00');
    expect(formatCostUsd(0.0004)).toBe('< $0.001');
    expect(formatCostUsd(0.048)).toBe('$0.048');
    expect(formatCostUsd(1.2345)).toBe('$1.235');
  });

  it('throttles incoming patches and commits in batches after throttleMs', () => {
    const engine = createThrottledSnapshotEngine({ throttleMs: 300, maxPendingPatches: 20 });
    const onBatchCommit = vi.fn();

    // 接收 3 个连续 chunk 补丁
    engine.queuePatch({ turnId: '1', chunkText: 'Hello ', tokenDelta: 2, timestamp: 1 }, onBatchCommit);
    engine.queuePatch({ turnId: '1', chunkText: 'World', tokenDelta: 2, timestamp: 2 }, onBatchCommit);
    engine.queuePatch({ turnId: '1', chunkText: '!', tokenDelta: 1, timestamp: 3 }, onBatchCommit);

    // 定时器前不应触发提交
    expect(onBatchCommit).not.toHaveBeenCalled();

    // 快进 300ms
    vi.advanceTimersByTime(300);

    expect(onBatchCommit).toHaveBeenCalledTimes(1);
    expect(onBatchCommit).toHaveBeenCalledWith('Hello World!', 5);

    const metrics = engine.getMetrics();
    expect(metrics.totalPatchesReceived).toBe(3);
    expect(metrics.snapshotsCommitted).toBe(1);
    expect(metrics.redundantSnapshotsPrevented).toBe(2);
    expect(metrics.reductionRatePercentage).toBe(67);
  });

  it('flushes immediately when maxPendingPatches is reached', () => {
    const engine = createThrottledSnapshotEngine({ throttleMs: 500, maxPendingPatches: 3 });
    const onBatchCommit = vi.fn();

    engine.queuePatch({ turnId: '1', chunkText: 'A', tokenDelta: 1, timestamp: 1 }, onBatchCommit);
    engine.queuePatch({ turnId: '1', chunkText: 'B', tokenDelta: 1, timestamp: 2 }, onBatchCommit);
    expect(onBatchCommit).not.toHaveBeenCalled();

    // 第 3 个补丁达到上限，立即冲刷
    engine.queuePatch({ turnId: '1', chunkText: 'C', tokenDelta: 1, timestamp: 3 }, onBatchCommit);
    expect(onBatchCommit).toHaveBeenCalledTimes(1);
    expect(onBatchCommit).toHaveBeenCalledWith('ABC', 3);
  });

  it('clears pending timer and metrics when clear is invoked', () => {
    const engine = createThrottledSnapshotEngine({ throttleMs: 300, maxPendingPatches: 10 });
    const onBatchCommit = vi.fn();

    engine.queuePatch({ turnId: '1', chunkText: 'Test', tokenDelta: 1, timestamp: 1 }, onBatchCommit);
    engine.clear();

    vi.advanceTimersByTime(500);
    expect(onBatchCommit).not.toHaveBeenCalled();
    expect(engine.getMetrics().totalPatchesReceived).toBe(0);
  });
});
