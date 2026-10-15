import { describe, it, expect, beforeEach, vi } from 'vitest';
import { useVisualTourStore } from '../useVisualTourStore';
import { DEFAULT_PLAYGROUND_TEMPLATES } from '../visualTourEngine';

describe('useVisualTourStore', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    useVisualTourStore.getState().resetOnboardingState();
  });

  it('初始调用 resetOnboardingState 后应重置为激活导览与初始清单状态', () => {
    const state = useVisualTourStore.getState();
    expect(state.isTourActive).toBe(true);
    expect(state.currentStepIndex).toBe(0);
    expect(state.isTourDismissed).toBe(false);
    expect(state.isChecklistDismissed).toBe(false);
    expect(state.checklistItems.length).toBeGreaterThan(0);
  });

  it('导览步骤递进与边界递退应正确变更索引', () => {
    const store = useVisualTourStore.getState();
    store.nextTourStep();
    expect(useVisualTourStore.getState().currentStepIndex).toBe(1);

    store.prevTourStep();
    expect(useVisualTourStore.getState().currentStepIndex).toBe(0);

    // 边界下再退依然为 0
    store.prevTourStep();
    expect(useVisualTourStore.getState().currentStepIndex).toBe(0);
  });

  it('在最后一步调用 nextTourStep 或 finishTour 应结束漫游并标记已完成', () => {
    const store = useVisualTourStore.getState();
    const total = store.steps.length;
    for (let i = 0; i < total; i++) {
      useVisualTourStore.getState().nextTourStep();
    }
    const finalState = useVisualTourStore.getState();
    expect(finalState.isTourActive).toBe(false);
    expect(finalState.isTourDismissed).toBe(true);
  });

  it('skipTour 应关闭漫游并持久化记录', () => {
    const store = useVisualTourStore.getState();
    store.skipTour();
    const state = useVisualTourStore.getState();
    expect(state.isTourActive).toBe(false);
    expect(state.isTourDismissed).toBe(true);
  });

  it('toggleChecklistItem 与 setChecklistItemCompleted 应正确更新清单项完成态', () => {
    const store = useVisualTourStore.getState();
    const firstItem = store.checklistItems[0];
    expect(firstItem).toBeDefined();
    if (firstItem) {
      expect(firstItem.completed).toBe(false);

      store.toggleChecklistItem(firstItem.id);
      expect(useVisualTourStore.getState().checklistItems[0]?.completed).toBe(true);

      store.setChecklistItemCompleted(firstItem.id, false);
      expect(useVisualTourStore.getState().checklistItems[0]?.completed).toBe(false);
    }
  });

  it('setChecklistCollapsed 与 setChecklistDismissed 应正确更新视图状态', () => {
    const store = useVisualTourStore.getState();
    store.setChecklistCollapsed(true);
    expect(useVisualTourStore.getState().isChecklistCollapsed).toBe(true);

    store.setChecklistDismissed(true);
    expect(useVisualTourStore.getState().isChecklistDismissed).toBe(true);
  });

  it('selectTemplate 应正确选中沙盒模板', () => {
    const store = useVisualTourStore.getState();
    const template = DEFAULT_PLAYGROUND_TEMPLATES[0];
    expect(template).toBeDefined();
    if (template) {
      store.selectTemplate(template);
      expect(useVisualTourStore.getState().selectedTemplate?.id).toBe(template.id);

      store.selectTemplate(null);
      expect(useVisualTourStore.getState().selectedTemplate).toBeNull();
    }
  });
});
