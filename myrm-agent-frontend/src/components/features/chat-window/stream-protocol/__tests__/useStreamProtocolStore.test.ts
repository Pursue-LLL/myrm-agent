import { describe, it, expect, beforeEach } from 'vitest';
import { useStreamProtocolStore } from '../useStreamProtocolStore';

describe('useStreamProtocolStore', () => {
  beforeEach(() => {
    useStreamProtocolStore.getState().resetStream();
  });

  it('initializes with clean state on reset', () => {
    const state = useStreamProtocolStore.getState();
    expect(state.streamContent).toBe('');
    expect(state.typedBlocks).toEqual([]);
    expect(state.viewport.anchorMode).toBe('PINNED_BOTTOM');
    expect(state.isStreaming).toBe(false);
    expect(state.isBenchmarkModalOpen).toBe(false);
  });

  it('appends stream chunks incrementally and updates blocks', () => {
    const store = useStreamProtocolStore.getState();
    store.appendStreamChunk('Hello **World** from stream!\n');

    let state = useStreamProtocolStore.getState();
    expect(state.streamContent).toContain('Hello **World**');
    expect(state.typedBlocks.length).toBeGreaterThanOrEqual(1);
    expect(state.isStreaming).toBe(true);
    expect(state.metrics.tokenCount).toBeGreaterThan(0);

    // 再次追加代码块
    store.appendStreamChunk('```javascript\nconst x = 42;\n```');
    state = useStreamProtocolStore.getState();
    expect(state.typedBlocks.some((b) => b.type === 'code_block')).toBe(true);
  });

  it('handles user scroll and switches viewport anchor mode', () => {
    const store = useStreamProtocolStore.getState();
    store.setStreamContent('Line 1\nLine 2\nLine 3\nLine 4\nLine 5\n'.repeat(20));

    // 模拟向上滚动脱离底部
    store.handleScroll(100);
    let state = useStreamProtocolStore.getState();
    expect(state.viewport.scrollTop).toBe(100);

    // 模拟滚回底部
    store.handleScroll(state.viewport.scrollHeight);
    state = useStreamProtocolStore.getState();
    expect(state.viewport.anchorMode).toBe('PINNED_BOTTOM');
  });

  it('handles window resize and adjusts viewport height', () => {
    const store = useStreamProtocolStore.getState();
    store.handleResize(900);

    const state = useStreamProtocolStore.getState();
    expect(state.viewport.clientHeight).toBe(900);
  });

  it('manages benchmark modal state and runs performance benchmark', () => {
    const store = useStreamProtocolStore.getState();
    expect(store.isBenchmarkModalOpen).toBe(false);

    store.openBenchmarkModal();
    expect(useStreamProtocolStore.getState().isBenchmarkModalOpen).toBe(true);

    const customText = 'Performance stress testing content.\n'.repeat(100);
    const benchmarkResult = store.runBenchmark(customText);

    expect(benchmarkResult.tokenCount).toBeGreaterThan(200);
    expect(benchmarkResult.throughputTokensPerSec).toBeGreaterThan(0);
    expect(benchmarkResult.parseDurationMs).toBeGreaterThanOrEqual(0.01);

    store.closeBenchmarkModal();
    expect(useStreamProtocolStore.getState().isBenchmarkModalOpen).toBe(false);
  });
});
