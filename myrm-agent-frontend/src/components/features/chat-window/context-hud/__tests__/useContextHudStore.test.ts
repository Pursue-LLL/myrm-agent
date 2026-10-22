import { describe, it, expect, beforeEach } from 'vitest';
import { useContextHudStore } from '../useContextHudStore';

describe('useContextHudStore', () => {
  beforeEach(() => {
    useContextHudStore.getState().resetStore();
  });

  it('initializes with default empty state', () => {
    const state = useContextHudStore.getState();
    expect(state.metricsByChatId).toEqual({});
    expect(state.attributionReports).toEqual({});
    expect(state.activeChatId).toBeNull();
    expect(state.isPopoverOpen).toBe(false);
  });

  it('updates metrics and generates attribution report for a chat session', () => {
    useContextHudStore.getState().updateMetrics('chat-abc', {
      inputTokens: 15000,
      outputTokens: 2500,
      cachedReadTokens: 12000,
      turnIndex: 3,
    });

    const metrics = useContextHudStore.getState().metricsByChatId['chat-abc'];
    expect(metrics).toBeDefined();
    expect(metrics.inputTokens).toBe(15000);
    expect(metrics.usedTokens).toBe(17500);
    expect(metrics.cacheHitRate).toBe(80);

    const report = useContextHudStore.getState().attributionReports['chat-abc'];
    expect(report).toBeDefined();
    expect(report.score).toBe(100);
  });

  it('manages activeChatId and popover open states', () => {
    useContextHudStore.getState().setActiveChatId('chat-active');
    expect(useContextHudStore.getState().activeChatId).toBe('chat-active');

    useContextHudStore.getState().togglePopover(true);
    expect(useContextHudStore.getState().isPopoverOpen).toBe(true);

    useContextHudStore.getState().togglePopover(false);
    expect(useContextHudStore.getState().isPopoverOpen).toBe(false);

    useContextHudStore.getState().togglePopover();
    expect(useContextHudStore.getState().isPopoverOpen).toBe(true);
  });

  it('clears specific chat metrics and diagnostics', () => {
    useContextHudStore.getState().updateMetrics('chat-clear', {
      inputTokens: 1000,
      outputTokens: 200,
      cachedReadTokens: 500,
    });
    expect(useContextHudStore.getState().metricsByChatId['chat-clear']).toBeDefined();

    useContextHudStore.getState().clearChatMetrics('chat-clear');
    expect(useContextHudStore.getState().metricsByChatId['chat-clear']).toBeUndefined();
    expect(useContextHudStore.getState().attributionReports['chat-clear']).toBeUndefined();
  });

  it('triggers auto compact and reduces input tokens while setting state active', () => {
    useContextHudStore.getState().updateMetrics('chat-compact', {
      inputTokens: 50000,
      outputTokens: 5000,
      cachedReadTokens: 20000,
      contextLimit: 100000,
    });

    useContextHudStore.getState().triggerAutoCompact('chat-compact');

    const compacted = useContextHudStore.getState().metricsByChatId['chat-compact'];
    expect(compacted.inputTokens).toBe(30000); // 50000 * 0.6
    expect(compacted.autoCompactState).toBe('active');
    expect(compacted.watermarkPercentage).toBe(35); // (30000 + 5000) / 100000
  });
});
