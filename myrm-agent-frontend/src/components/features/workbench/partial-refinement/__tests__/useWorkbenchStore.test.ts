import { describe, it, expect, beforeEach, vi } from 'vitest';
import { useWorkbenchStore } from '../useWorkbenchStore';
import { SelectionRange, WorkbenchTab } from '../workbenchTypes';

describe('useWorkbenchStore Zustand state store', () => {
  beforeEach(() => {
    useWorkbenchStore.getState().resetState();
  });

  it('initializes with default tabs and docked state', () => {
    const state = useWorkbenchStore.getState();
    expect(state.tabs.length).toBeGreaterThanOrEqual(4);
    expect(state.activeTabId).toBe('tab-doc-1');
    expect(state.isDocked).toBe(true);
    expect(state.currentSelection).toBeNull();
    expect(state.refinementStatus).toBe('idle');
    expect(state.tokenStats.totalRefinements).toBe(3);
  });

  it('handles openTab, switchTab and closeTab operations', () => {
    const newTab: WorkbenchTab = {
      id: 'tab-custom-1',
      title: 'custom-notes.txt',
      type: 'document',
      content: 'Custom notes body',
    };

    useWorkbenchStore.getState().openTab(newTab);
    expect(useWorkbenchStore.getState().activeTabId).toBe('tab-custom-1');
    expect(useWorkbenchStore.getState().tabs.some((t) => t.id === 'tab-custom-1')).toBe(true);

    useWorkbenchStore.getState().switchTab('tab-doc-1');
    expect(useWorkbenchStore.getState().activeTabId).toBe('tab-doc-1');

    useWorkbenchStore.getState().closeTab('tab-custom-1');
    expect(useWorkbenchStore.getState().tabs.some((t) => t.id === 'tab-custom-1')).toBe(false);
  });

  it('updates tab content and flags tab as modified', () => {
    useWorkbenchStore.getState().updateTabContent('tab-doc-1', 'Updated content text');
    const tab = useWorkbenchStore.getState().tabs.find((t) => t.id === 'tab-doc-1');

    expect(tab?.content).toBe('Updated content text');
    expect(tab?.isModified).toBe(true);
  });

  it('toggles workbench docking state', () => {
    expect(useWorkbenchStore.getState().isDocked).toBe(true);
    useWorkbenchStore.getState().toggleDock();
    expect(useWorkbenchStore.getState().isDocked).toBe(false);
  });

  it('manages text selection and lifecycle transitions', () => {
    const range: SelectionRange = {
      startOffset: 10,
      endOffset: 30,
      selectedText: '智能体算力需求在2026年',
      contextBefore: '',
      contextAfter: '',
    };

    useWorkbenchStore.getState().setSelection(range);
    expect(useWorkbenchStore.getState().currentSelection).toEqual(range);
    expect(useWorkbenchStore.getState().refinementStatus).toBe('prompting');

    useWorkbenchStore.getState().setSelection(null);
    expect(useWorkbenchStore.getState().currentSelection).toBeNull();
    expect(useWorkbenchStore.getState().refinementStatus).toBe('idle');
  });

  it('executes in-place refinement workflow, applies patch and dispatches event', async () => {
    const dispatchSpy = vi.spyOn(window, 'dispatchEvent');

    const sampleText = '预计在金融与政企市场保持激进扩张节奏，年度ARR增长率预计超过180%。';
    const range: SelectionRange = {
      startOffset: 0,
      endOffset: sampleText.length,
      selectedText: sampleText,
      contextBefore: '',
      contextAfter: '',
    };

    useWorkbenchStore.getState().setSelection(range);

    const taskPromise = useWorkbenchStore.getState().startRefinement('改为保守估值，补充汇率风险');
    expect(useWorkbenchStore.getState().refinementStatus).toBe('refining');

    const task = await taskPromise;
    expect(task).not.toBeNull();
    expect(useWorkbenchStore.getState().refinementStatus).toBe('previewing');
    expect(task?.refinedChunk).toContain('稳健增长');

    // Apply the refinement
    useWorkbenchStore.getState().applyRefinement();

    const activeTab = useWorkbenchStore.getState().tabs.find((t) => t.id === 'tab-doc-1');
    expect(activeTab?.content).toContain('稳健增长');
    expect(useWorkbenchStore.getState().refinementStatus).toBe('applied');
    expect(useWorkbenchStore.getState().tokenStats.totalRefinements).toBe(4);
    expect(useWorkbenchStore.getState().tokenStats.totalTokensSaved).toBeGreaterThan(14200);

    expect(dispatchSpy).toHaveBeenCalledWith(
      expect.objectContaining({
        type: 'myrm:partial-refinement-applied',
      })
    );

    dispatchSpy.mockRestore();
  });

  it('rejects in-place refinement cleanly without modifying tab content', () => {
    const range: SelectionRange = {
      startOffset: 0,
      endOffset: 10,
      selectedText: 'test-text',
      contextBefore: '',
      contextAfter: '',
    };

    useWorkbenchStore.getState().setSelection(range);
    useWorkbenchStore.getState().rejectRefinement();

    expect(useWorkbenchStore.getState().refinementStatus).toBe('rejected');
    expect(useWorkbenchStore.getState().currentSelection).toBeNull();
    expect(useWorkbenchStore.getState().currentRefinementTask).toBeNull();
  });
});
