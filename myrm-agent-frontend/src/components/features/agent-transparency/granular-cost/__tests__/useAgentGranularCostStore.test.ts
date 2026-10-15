import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { useAgentGranularCostStore } from '../useAgentGranularCostStore';

describe('useAgentGranularCostStore', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    useAgentGranularCostStore.getState().reset();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('initializes with default agent profiles and throttle configuration', () => {
    const state = useAgentGranularCostStore.getState();
    expect(state.agentProfiles.length).toBe(3);
    expect(state.throttleConfig.throttleMs).toBe(300);
    expect(state.currentStreamBuffer).toBe('');
    expect(state.throttleMetrics.totalPatchesReceived).toBe(0);
  });

  it('sets and clears active hovered agent id', () => {
    const { setActiveHoveredAgentId } = useAgentGranularCostStore.getState();

    setActiveHoveredAgentId('agent-planner');
    expect(useAgentGranularCostStore.getState().activeHoveredAgentId).toBe('agent-planner');

    setActiveHoveredAgentId(null);
    expect(useAgentGranularCostStore.getState().activeHoveredAgentId).toBeNull();
  });

  it('records agent token usage and computes new cost accurately', () => {
    const { recordAgentUsage } = useAgentGranularCostStore.getState();

    // 针对 agent-planner 增量累计 10k prompt, 2k completion
    const initialProfile = useAgentGranularCostStore
      .getState()
      .agentProfiles.find((p) => p.agentId === 'agent-planner');
    const initialTotal = initialProfile?.totalTokens || 0;

    recordAgentUsage('agent-planner', 10000, 2000, 5000);

    const updatedProfile = useAgentGranularCostStore
      .getState()
      .agentProfiles.find((p) => p.agentId === 'agent-planner');

    expect(updatedProfile?.totalTokens).toBe(initialTotal + 12000);
    expect(updatedProfile?.cachedTokens).toBe((initialProfile?.cachedTokens || 0) + 5000);
    expect(updatedProfile?.estimatedCostUsd).toBeGreaterThan(initialProfile?.estimatedCostUsd || 0);
    expect(updatedProfile?.historyPoints.length).toBeGreaterThan(0);
  });

  it('dispatches streaming chunks and accumulates text with throttled commit', () => {
    const { dispatchStreamingChunk } = useAgentGranularCostStore.getState();

    dispatchStreamingChunk('agent-coder', {
      turnId: 'turn-1',
      chunkText: 'const x = ',
      tokenDelta: 3,
      timestamp: 1,
    });

    dispatchStreamingChunk('agent-coder', {
      turnId: 'turn-1',
      chunkText: '42;',
      tokenDelta: 2,
      timestamp: 2,
    });

    // 定时器前 buffer 尚未被批量提交
    expect(useAgentGranularCostStore.getState().currentStreamBuffer).toBe('');

    // 快进 300ms 触发批量快照提交
    vi.advanceTimersByTime(300);

    const state = useAgentGranularCostStore.getState();
    expect(state.currentStreamBuffer).toBe('const x = 42;');
    expect(state.throttleMetrics.snapshotsCommitted).toBe(1);
  });

  it('flushes streaming buffer manually and updates agent profile', () => {
    const { dispatchStreamingChunk, flushStreamingBuffer } =
      useAgentGranularCostStore.getState();

    dispatchStreamingChunk('agent-reviewer', {
      turnId: 'turn-2',
      chunkText: 'Check passed',
      tokenDelta: 2,
      timestamp: 1,
    });

    flushStreamingBuffer('agent-reviewer');

    expect(useAgentGranularCostStore.getState().currentStreamBuffer).toBe('Check passed');
  });

  it('updates throttle config and resets state', () => {
    const { updateThrottleConfig, reset } = useAgentGranularCostStore.getState();

    updateThrottleConfig({ throttleMs: 500 });
    expect(useAgentGranularCostStore.getState().throttleConfig.throttleMs).toBe(500);

    reset();
    expect(useAgentGranularCostStore.getState().currentStreamBuffer).toBe('');
  });
});
