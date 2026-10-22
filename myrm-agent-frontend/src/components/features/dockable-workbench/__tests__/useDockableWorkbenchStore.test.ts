import { describe, it, expect, beforeEach } from 'vitest';
import { useDockableWorkbenchStore } from '../useDockableWorkbenchStore';
import type { BootstrapSessionPayload } from '../dockableWorkbenchTypes';

describe('useDockableWorkbenchStore', () => {
  beforeEach(() => {
    useDockableWorkbenchStore.getState().resetStore();
  });

  it('初始状态应包含默认面板设置与基线', () => {
    const state = useDockableWorkbenchStore.getState();
    expect(state.activePanelId).toBe('changes');
    expect(state.dockPosition).toBe('right');
    expect(state.isCollapsed).toBe(false);
    expect(state.connectionEpoch).toBe(1);
    expect(state.changesList.length).toBeGreaterThan(0);
  });

  it('openPanel, closePanel 与 setDockPosition 能正确切换停靠面板与方位', () => {
    const store = useDockableWorkbenchStore.getState();
    store.openPanel('live_browser', 'bottom');

    let state = useDockableWorkbenchStore.getState();
    expect(state.activePanelId).toBe('live_browser');
    expect(state.dockPosition).toBe('bottom');

    store.closePanel();
    state = useDockableWorkbenchStore.getState();
    expect(state.activePanelId).toBeNull();
    expect(state.dockPosition).toBe('closed');
  });

  it('toggleCollapse 能切换折叠与展开状态', () => {
    const store = useDockableWorkbenchStore.getState();
    store.toggleCollapse();
    expect(useDockableWorkbenchStore.getState().isCollapsed).toBe(true);

    store.toggleCollapse();
    expect(useDockableWorkbenchStore.getState().isCollapsed).toBe(false);
  });

  it('updateTaskEvent 能够更新任务状态，并拒绝旧代次乱序事件', () => {
    const store = useDockableWorkbenchStore.getState();
    // 正常顺序事件
    const success = store.updateTaskEvent({
      taskId: 'task-1',
      status: 'running',
      currentTool: 'edit_file',
      stepIndex: 1,
      totalSteps: 3,
      progressPercentage: 33,
      epoch: 1,
      sequenceNo: 1,
    });
    expect(success).toBe(true);
    expect(useDockableWorkbenchStore.getState().currentTask?.stepIndex).toBe(1);

    // 重置代次至 2
    store.resetEpochBaseline(2);

    // 旧代次 1 的事件应被拒绝
    const oldRejected = store.updateTaskEvent({
      taskId: 'task-1',
      status: 'running',
      currentTool: 'edit_file',
      stepIndex: 2,
      totalSteps: 3,
      progressPercentage: 66,
      epoch: 1,
      sequenceNo: 2,
    });
    expect(oldRejected).toBe(false);
    expect(useDockableWorkbenchStore.getState().currentTask?.stepIndex).toBe(1);
  });

  it('applyBootstrapPayload 能原子更新聚合会话信息与基线代次', () => {
    const store = useDockableWorkbenchStore.getState();
    const mockPayload: BootstrapSessionPayload = {
      sessionId: 'sess-fast-002',
      sessionTitle: '极速聚合会话',
      activeAgentName: '高并发管家',
      sandboxChanges: [
        {
          path: 'src/main.ts',
          changeType: 'modified',
          additions: 10,
          deletions: 2,
          diffHunk: '@@ -1 +1 @@',
        },
      ],
      eventBaselineEpoch: 3,
      initialMessagesCount: 50,
      cachedAt: '2026-10-15T18:00:00Z',
    };

    store.applyBootstrapPayload(mockPayload);
    const state = useDockableWorkbenchStore.getState();
    expect(state.bootstrapData?.sessionId).toBe('sess-fast-002');
    expect(state.changesList.length).toBe(1);
    expect(state.connectionEpoch).toBe(3);
    expect(state.lastSequenceNo).toBe(0);
  });
});
