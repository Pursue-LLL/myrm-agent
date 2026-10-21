import { describe, it, expect, beforeEach, vi } from 'vitest';
import { useThinkingBudgetStore } from '../useThinkingBudgetStore';
import * as legacyIntensity from '@/components/features/message-input-actions/ThinkingIntensityButton';

describe('useThinkingBudgetStore', () => {
  beforeEach(() => {
    localStorage.clear();
    useThinkingBudgetStore.setState({
      level: 'off',
      currentModel: '',
      tokenBudget: 0,
      reasoningEffort: undefined,
    });
    vi.restoreAllMocks();
  });

  it('initializes with default off tier and 0 token budget', () => {
    const state = useThinkingBudgetStore.getState();
    expect(state.level).toBe('off');
    expect(state.tokenBudget).toBe(0);
    expect(state.reasoningEffort).toBeUndefined();
  });

  it('updates level, token budget, and syncs legacy intensity bus', () => {
    const spySetGlobal = vi.spyOn(legacyIntensity, 'setGlobalIntensity');
    const { setLevel } = useThinkingBudgetStore.getState();

    setLevel('medium', 'claude-3-7-sonnet');

    const state = useThinkingBudgetStore.getState();
    expect(state.level).toBe('medium');
    expect(state.tokenBudget).toBe(8192);
    expect(state.reasoningEffort).toBe('medium');
    expect(spySetGlobal).toHaveBeenCalledWith('medium', 'claude-3-7-sonnet');
    expect(localStorage.getItem('myrm_thinking_budget_claude-3-7-sonnet')).toBe('medium');
  });

  it('hydrates stored level when switching to an existing model', () => {
    localStorage.setItem('myrm_thinking_budget_o3-mini', 'high');
    const { hydrateForModel } = useThinkingBudgetStore.getState();

    hydrateForModel('o3-mini');

    const state = useThinkingBudgetStore.getState();
    expect(state.currentModel).toBe('o3-mini');
    expect(state.level).toBe('high');
    expect(state.tokenBudget).toBe(16384);
    expect(state.reasoningEffort).toBe('high');
  });

  it('removes storage entry when setting level to off', () => {
    localStorage.setItem('myrm_thinking_budget_gpt-4o', 'low');
    const { setLevel } = useThinkingBudgetStore.getState();

    setLevel('off', 'gpt-4o');

    expect(localStorage.getItem('myrm_thinking_budget_gpt-4o')).toBeNull();
  });
});
