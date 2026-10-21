import { describe, expect, it, beforeEach } from 'vitest';
import { useCommGraphStore } from '../useCommGraphStore';

describe('useCommGraphStore', () => {
  beforeEach(() => {
    useCommGraphStore.getState().resetState();
  });

  it('初始状态 events 为空，严格保证 isLive 为 false，杜绝死锁卡死误导', () => {
    const state = useCommGraphStore.getState();
    expect(state.events).toEqual([]);
    expect(state.isLive).toBe(false);
    expect(state.selectedEventId).toBeNull();
    expect(state.returnCursorId).toBeNull();
    expect(state.isPipelineInitializing).toBe(true);

    // 当 events 为空时，toggleLive 应该被安全防卫，严禁激活 isLive
    state.toggleLive();
    expect(useCommGraphStore.getState().isLive).toBe(false);
  });

  it('添加事件后自动退出流水线初始化态，并在非 Live 模式下维持当前选择', () => {
    const store = useCommGraphStore.getState();
    const id1 = store.addCommEvent({
      stepIndex: 1,
      fromAgent: 'AgentA',
      toAgent: 'AgentB',
      action: 'init_plan',
      payloadSummary: '初始计划',
      status: 'completed',
    });

    let state = useCommGraphStore.getState();
    expect(state.events.length).toBe(1);
    expect(state.selectedEventId).toBe(id1);
    expect(state.isPipelineInitializing).toBe(false);

    // 手动选定 id1，且处于历史审阅模式 (isLive = false)
    store.selectEvent(id1);

    // 追加第二个事件
    const id2 = store.addCommEvent({
      stepIndex: 2,
      fromAgent: 'AgentB',
      toAgent: 'AgentC',
      action: 'execute_step',
      payloadSummary: '执行第二步',
      status: 'completed',
    });

    state = useCommGraphStore.getState();
    expect(state.events.length).toBe(2);
    // 因为 isLive 为 false，用户的视角应保持在原先选定的 id1，不被强制跳到最新
    expect(state.selectedEventId).toBe(id1);
    expect(state.events[1].id).toBe(id2);
  });

  it('Live 双向游标记忆防丢失：从历史切入 Live 会记录 returnCursorId，再次切回可原位恢复', () => {
    const store = useCommGraphStore.getState();
    const id1 = store.addCommEvent({
      stepIndex: 1,
      fromAgent: 'AgentA',
      toAgent: 'AgentB',
      action: 'step_1',
      payloadSummary: '步骤1',
      status: 'completed',
    });
    const id2 = store.addCommEvent({
      stepIndex: 2,
      fromAgent: 'AgentB',
      toAgent: 'AgentC',
      action: 'step_2',
      payloadSummary: '步骤2',
      status: 'completed',
    });

    // 用户正在审阅步骤 1
    store.selectEvent(id1);
    expect(useCommGraphStore.getState().selectedEventId).toBe(id1);
    expect(useCommGraphStore.getState().isLive).toBe(false);

    // 第一次点击 toggleLive: 切入实时最新视角
    store.toggleLive();
    let state = useCommGraphStore.getState();
    expect(state.isLive).toBe(true);
    expect(state.selectedEventId).toBe(id2);
    expect(state.returnCursorId).toBe(id1); // 成功暂存历史游标！

    // 第二次点击 toggleLive: 退出实时视角，原位回溯到步骤 1
    store.toggleLive();
    state = useCommGraphStore.getState();
    expect(state.isLive).toBe(false);
    expect(state.selectedEventId).toBe(id1); // 成功恢复至步骤 1！
    expect(state.returnCursorId).toBeNull();
  });

  it('清空事件与重置状态能够恢复初始隔离态', () => {
    const store = useCommGraphStore.getState();
    store.addCommEvent({
      stepIndex: 1,
      fromAgent: 'AgentA',
      toAgent: 'AgentB',
      action: 'temp',
      payloadSummary: '临时',
      status: 'completed',
    });

    expect(useCommGraphStore.getState().events.length).toBe(1);

    store.clearEvents();
    const state = useCommGraphStore.getState();
    expect(state.events).toEqual([]);
    expect(state.selectedEventId).toBeNull();
    expect(state.isLive).toBe(false);
    expect(state.isPipelineInitializing).toBe(true);
  });
});
