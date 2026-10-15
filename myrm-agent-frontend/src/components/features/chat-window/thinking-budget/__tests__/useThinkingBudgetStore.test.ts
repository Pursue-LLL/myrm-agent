import { describe, it, expect, beforeEach } from 'vitest';
import { useThinkingBudgetStore } from '../useThinkingBudgetStore';

describe('useThinkingBudgetStore', () => {
  beforeEach(() => {
    useThinkingBudgetStore.getState().reset();
  });

  it('initializes with default budget level and thinking states', () => {
    const state = useThinkingBudgetStore.getState();
    expect(state.currentBudgetLevel).toBe('medium');
    expect(state.isThinkingCapable).toBe(true);
    expect(state.isSelectorOpen).toBe(false);
    expect(state.isThinking).toBe(false);
    expect(state.isExpanded).toBe(false);
    expect(state.stages.length).toBeGreaterThan(0);
  });

  it('switches budget level and closes selector', () => {
    const { setBudgetLevel, toggleSelector } = useThinkingBudgetStore.getState();

    toggleSelector(true);
    expect(useThinkingBudgetStore.getState().isSelectorOpen).toBe(true);

    setBudgetLevel('high');
    expect(useThinkingBudgetStore.getState().currentBudgetLevel).toBe('high');
    expect(useThinkingBudgetStore.getState().isSelectorOpen).toBe(false);
  });

  it('toggles thinking capability and box expansion', () => {
    const { setIsThinkingCapable, toggleExpanded } =
      useThinkingBudgetStore.getState();

    setIsThinkingCapable(false);
    expect(useThinkingBudgetStore.getState().isThinkingCapable).toBe(false);

    toggleExpanded(true);
    expect(useThinkingBudgetStore.getState().isExpanded).toBe(true);

    toggleExpanded(false);
    expect(useThinkingBudgetStore.getState().isExpanded).toBe(false);
  });

  it('manages thinking lifecycle from start, append chunk, to finish', () => {
    const { startThinking, appendThinkingChunk, finishThinking } =
      useThinkingBudgetStore.getState();

    startThinking();
    let state = useThinkingBudgetStore.getState();
    expect(state.isThinking).toBe(true);
    expect(state.totalElapsedSec).toBe(0);
    expect(state.thinkingTokens).toBe(0);
    expect(state.rawContent).toBe('');

    appendThinkingChunk('[阶段 1: 需求澄清]\n明确系统 SLA 指标', 8, 1.5);
    state = useThinkingBudgetStore.getState();
    expect(state.thinkingTokens).toBe(8);
    expect(state.totalElapsedSec).toBe(1.5);
    expect(state.stages.length).toBe(1);

    finishThinking();
    state = useThinkingBudgetStore.getState();
    expect(state.isThinking).toBe(false);
    expect(state.stages[0].status).toBe('completed');
  });
});
