import { describe, expect, it, beforeEach } from 'vitest';
import { useRealLinkAlignmentStore } from '../useRealLinkAlignmentStore';

describe('useRealLinkAlignmentStore', () => {
  beforeEach(() => {
    useRealLinkAlignmentStore.getState().resetState();
  });

  it('初始状态具备默认三只松鼠落地页代码与待对齐链接，计算出初始对齐率', () => {
    const state = useRealLinkAlignmentStore.getState();
    expect(state.detectedLinks.length).toBe(4);
    // 4 个链接中：投递(#)、客服(javascript:void)、商城(example.com) 为假，文档为真
    expect(state.alignmentRate).toBe(25);
    expect(state.isApplied).toBe(false);
  });

  it('能够单项对齐某个特定链接并更新整体对齐率', () => {
    const store = useRealLinkAlignmentStore.getState();
    const firstPlaceholder = store.detectedLinks.find(
      (l) => l.status === 'placeholder_detected'
    );
    expect(firstPlaceholder).not.toBeUndefined();

    if (firstPlaceholder) {
      store.alignLinkToRealEntity(
        firstPlaceholder.id,
        'https://careers.3squirrels.com/campus',
        '三只松鼠校招官网'
      );
    }

    const updated = useRealLinkAlignmentStore.getState();
    const target = updated.detectedLinks.find(
      (l) => l.id === firstPlaceholder?.id
    );
    expect(target?.status).toBe('aligned');
    expect(target?.targetEntityName).toBe('三只松鼠校招官网');
    // 2/4 = 50%
    expect(updated.alignmentRate).toBe(50);
  });

  it('一键批量对齐将所有假链对齐到权威实体，对齐率跃升至 100%', () => {
    const store = useRealLinkAlignmentStore.getState();
    store.batchAlignPlaceholders();

    const updated = useRealLinkAlignmentStore.getState();
    expect(updated.alignmentRate).toBe(100);
    expect(
      updated.detectedLinks.every((l) => l.status === 'aligned')
    ).toBe(true);
  });

  it('applyAlignedCode 将对齐链接重写至源码并设置 isApplied 标记', () => {
    const store = useRealLinkAlignmentStore.getState();
    store.batchAlignPlaceholders();

    const newCode = store.applyAlignedCode();
    expect(newCode).toContain('https://careers.3squirrels.com/campus');
    expect(newCode).not.toContain('href="#"');
    expect(useRealLinkAlignmentStore.getState().isApplied).toBe(true);
  });

  it('resetState 能够重置为初始状态', () => {
    const store = useRealLinkAlignmentStore.getState();
    store.batchAlignPlaceholders();
    expect(useRealLinkAlignmentStore.getState().alignmentRate).toBe(100);

    store.resetState();
    expect(useRealLinkAlignmentStore.getState().alignmentRate).toBe(25);
    expect(useRealLinkAlignmentStore.getState().isApplied).toBe(false);
  });
});
