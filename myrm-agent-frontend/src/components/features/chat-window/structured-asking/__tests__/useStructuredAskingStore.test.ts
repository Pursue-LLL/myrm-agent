import { describe, it, expect, beforeEach } from 'vitest';
import { useStructuredAskingStore } from '../useStructuredAskingStore';

describe('useStructuredAskingStore', () => {
  beforeEach(() => {
    useStructuredAskingStore.getState().resetAll();
  });

  it('returns default draft state when questionId is not initialized', () => {
    const draft = useStructuredAskingStore.getState().getDraft('q1');
    expect(draft.selectedOptionIds).toEqual([]);
    expect(draft.textInput).toBe('');
  });

  it('handles single_choice and boolean_confirm option selection properly', () => {
    const store = useStructuredAskingStore.getState();

    // Single choice replaces selection
    store.selectOption('q_single', 'opt_a', 'single_choice');
    expect(useStructuredAskingStore.getState().getDraft('q_single').selectedOptionIds).toEqual(['opt_a']);

    store.selectOption('q_single', 'opt_b', 'single_choice');
    expect(useStructuredAskingStore.getState().getDraft('q_single').selectedOptionIds).toEqual(['opt_b']);

    // Boolean confirm replaces selection
    store.selectOption('q_bool', 'confirm_yes', 'boolean_confirm');
    expect(useStructuredAskingStore.getState().getDraft('q_bool').selectedOptionIds).toEqual(['confirm_yes']);

    store.selectOption('q_bool', 'confirm_no', 'boolean_confirm');
    expect(useStructuredAskingStore.getState().getDraft('q_bool').selectedOptionIds).toEqual(['confirm_no']);
  });

  it('handles multi_choice option toggling (append and remove)', () => {
    const store = useStructuredAskingStore.getState();

    store.selectOption('q_multi', 'opt_1', 'multi_choice');
    expect(useStructuredAskingStore.getState().getDraft('q_multi').selectedOptionIds).toEqual(['opt_1']);

    store.selectOption('q_multi', 'opt_2', 'multi_choice');
    expect(useStructuredAskingStore.getState().getDraft('q_multi').selectedOptionIds).toEqual(['opt_1', 'opt_2']);

    // Toggle off opt_1
    store.selectOption('q_multi', 'opt_1', 'multi_choice');
    expect(useStructuredAskingStore.getState().getDraft('q_multi').selectedOptionIds).toEqual(['opt_2']);
  });

  it('updates text input for text_slot or additional remarks', () => {
    const store = useStructuredAskingStore.getState();
    store.setTextInput('q_text', '优先满足响应延迟在 50ms 内');

    expect(useStructuredAskingStore.getState().getDraft('q_text').textInput).toBe('优先满足响应延迟在 50ms 内');
  });

  it('builds standard question response with selected options and text', () => {
    const store = useStructuredAskingStore.getState();
    store.selectOption('q_submit', 'opt_fast', 'single_choice');
    store.setTextInput('q_submit', '加急处理');

    const res = store.buildResponse('q_submit', false);
    expect(res.isSkipped).toBe(false);
    expect(res.selectedOptionIds).toEqual(['opt_fast']);
    expect(res.textValue).toBe('加急处理');
    expect(res.answeredAt).toBeGreaterThan(0);
  });

  it('builds skipped response falling back to default option when provided', () => {
    const store = useStructuredAskingStore.getState();
    store.selectOption('q_skip', 'opt_custom', 'single_choice');

    const res = store.buildResponse('q_skip', true, 'opt_default');
    expect(res.isSkipped).toBe(true);
    expect(res.selectedOptionIds).toEqual(['opt_default']);
    expect(res.textValue).toBeUndefined();
  });

  it('clears specific draft and resets all state', () => {
    const store = useStructuredAskingStore.getState();
    store.selectOption('q_1', 'opt_1', 'single_choice');
    store.selectOption('q_2', 'opt_2', 'single_choice');

    store.clearDraft('q_1');
    expect(useStructuredAskingStore.getState().getDraft('q_1').selectedOptionIds).toEqual([]);
    expect(useStructuredAskingStore.getState().getDraft('q_2').selectedOptionIds).toEqual(['opt_2']);

    store.resetAll();
    expect(useStructuredAskingStore.getState().drafts).toEqual({});
  });
});
