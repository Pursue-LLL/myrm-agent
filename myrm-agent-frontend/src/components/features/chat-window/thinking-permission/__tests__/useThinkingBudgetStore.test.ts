import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
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
    legacyIntensity.setGlobalIntensity('off');
  });

  afterEach(() => {
    vi.unstubAllGlobals();
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

  it('moves the intensity bus to the hydrated level', () => {
    localStorage.setItem('myrm_thinking_budget_o3-mini', 'high');
    legacyIntensity.setGlobalIntensity('low');

    useThinkingBudgetStore.getState().hydrateForModel('o3-mini');

    expect(legacyIntensity.getThinkingEffort()).toBe('high');
  });

  it('keeps the preference the intensity control saved for a model when switching to it', () => {
    localStorage.setItem('thinkingIntensity_o3-mini', 'max');
    legacyIntensity.setGlobalIntensity('high', 'gpt-4o');

    useThinkingBudgetStore.getState().hydrateForModel('o3-mini');

    expect(localStorage.getItem('thinkingIntensity_o3-mini')).toBe('max');
    expect(localStorage.getItem('thinkingIntensity_gpt-4o')).toBe('high');
  });

  it('keeps a custom value the intensity control saved for a model when switching to it', () => {
    localStorage.setItem('thinkingIntensityCustom_o3-mini', '24k');
    legacyIntensity.setGlobalIntensity('medium', 'gpt-4o');

    useThinkingBudgetStore.getState().hydrateForModel('o3-mini');

    expect(localStorage.getItem('thinkingIntensityCustom_o3-mini')).toBe('24k');
  });

  it('ignores hydration for an empty model name or the model already hydrated', () => {
    legacyIntensity.setGlobalIntensity('low');

    useThinkingBudgetStore.getState().hydrateForModel('');
    expect(useThinkingBudgetStore.getState().currentModel).toBe('');

    useThinkingBudgetStore.setState({ currentModel: 'o3-mini' });
    localStorage.setItem('myrm_thinking_budget_o3-mini', 'max');
    useThinkingBudgetStore.getState().hydrateForModel('o3-mini');

    expect(useThinkingBudgetStore.getState().level).toBe('off');
    expect(legacyIntensity.getThinkingEffort()).toBe('low');
  });

  it('falls back to off for an unrecognised stored level', () => {
    localStorage.setItem('myrm_thinking_budget_o3-mini', 'turbo');

    useThinkingBudgetStore.getState().hydrateForModel('o3-mini');

    expect(useThinkingBudgetStore.getState().level).toBe('off');
    expect(useThinkingBudgetStore.getState().tokenBudget).toBe(0);
  });

  it('still changes level when storage is blocked', () => {
    const refuse = () => {
      throw new DOMException('blocked', 'SecurityError');
    };
    vi.stubGlobal('localStorage', { getItem: refuse, setItem: refuse, removeItem: refuse });

    useThinkingBudgetStore.getState().hydrateForModel('blocked-model');
    useThinkingBudgetStore.getState().setLevel('high', 'blocked-model');

    expect(useThinkingBudgetStore.getState().currentModel).toBe('blocked-model');
    expect(useThinkingBudgetStore.getState().level).toBe('high');
    expect(legacyIntensity.getThinkingEffort()).toBe('high');
  });

  it('removes storage entry when setting level to off', () => {
    localStorage.setItem('myrm_thinking_budget_gpt-4o', 'low');
    const { setLevel } = useThinkingBudgetStore.getState();

    setLevel('off', 'gpt-4o');

    expect(localStorage.getItem('myrm_thinking_budget_gpt-4o')).toBeNull();
  });
});
