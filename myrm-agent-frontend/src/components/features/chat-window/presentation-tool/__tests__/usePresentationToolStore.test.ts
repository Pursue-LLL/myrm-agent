import { beforeEach, describe, expect, it } from 'vitest';
import { PresentationPayload, SuggestionChipItem } from '../presentationToolTypes';
import { usePresentationToolStore } from '../usePresentationToolStore';

describe('usePresentationToolStore', () => {
  beforeEach(() => {
    usePresentationToolStore.getState().reset();
  });

  const mockPayload: PresentationPayload = {
    id: 'pres-101',
    toolName: 'present_products',
    title: '推荐商品列表',
    createdAt: Date.now(),
    items: [
      { id: 'item-1', title: 'iPhone 16', position: 1 },
      { id: 'item-2', title: 'iPhone 16 Pro', position: 2 },
    ],
  };

  it('initializes with default empty state', () => {
    const state = usePresentationToolStore.getState();
    expect(state.activePresentations).toEqual({});
    expect(state.selectedPositionalItem).toBeNull();
    expect(state.lastActionQuery).toBeNull();
  });

  it('registers presentation payload correctly', () => {
    usePresentationToolStore.getState().registerPresentation(mockPayload);
    const store = usePresentationToolStore.getState();
    expect(store.activePresentations['pres-101']).toEqual(mockPayload);
  });

  it('records action query when suggestion chip is clicked', () => {
    const chip: SuggestionChipItem = {
      id: 'chip-1',
      label: '导出清单',
      actionQuery: '请帮我导出明细清单',
      position: 1,
    };

    const action = usePresentationToolStore.getState().clickSuggestionChip(chip);
    expect(action).toBe('请帮我导出明细清单');
    expect(usePresentationToolStore.getState().lastActionQuery).toBe(
      '请帮我导出明细清单',
    );
  });

  it('resolves positional reference and updates selectedPositionalItem', () => {
    usePresentationToolStore.getState().registerPresentation(mockPayload);

    const res = usePresentationToolStore
      .getState()
      .resolveAndSelectItem('我要第 2 个', 'pres-101');

    expect(res.position).toBe(2);
    expect(res.matchedItem?.position).toBe(2);

    const store = usePresentationToolStore.getState();
    expect(store.selectedPositionalItem?.presentationId).toBe('pres-101');
    expect(store.selectedPositionalItem?.item.position).toBe(2);
  });

  it('handles non-existent presentationId gracefully', () => {
    const res = usePresentationToolStore
      .getState()
      .resolveAndSelectItem('选第一个', 'invalid-id');

    expect(res.matchedItem).toBeNull();
    expect(res.confidence).toBe(0);
    expect(res.rationale).toContain('未找到 ID 为 invalid-id 的展示负载');
  });

  it('clears and resets state properly', () => {
    usePresentationToolStore.getState().registerPresentation(mockPayload);
    usePresentationToolStore.getState().clickSuggestionChip({
      id: 'c',
      label: 'l',
      actionQuery: 'q',
      position: 1,
    });

    usePresentationToolStore.getState().clear();
    expect(usePresentationToolStore.getState().activePresentations).toEqual({});
    expect(usePresentationToolStore.getState().lastActionQuery).toBeNull();
  });
});
