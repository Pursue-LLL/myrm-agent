import { beforeEach, describe, expect, it } from 'vitest';
import { useAmbientActivityStore } from '../useAmbientActivityStore';

describe('useAmbientActivityStore', () => {
  beforeEach(() => {
    useAmbientActivityStore.getState().reset();
  });

  it('initializes with default state', () => {
    const state = useAmbientActivityStore.getState();
    expect(state.activities).toEqual({});
    expect(state.isInspectionDrawerOpen).toBe(false);
    expect(state.selectedActivityId).toBeNull();
    expect(state.isDeckCollapsed).toBe(false);
    expect(state.showHiddenBotsInSidebar).toBe(false);
  });

  it('records new bot activities correctly', () => {
    const id = useAmbientActivityStore.getState().recordActivity({
      sessionId: 'sess-100',
      sourceAgent: 'AgentA',
      targetAgent: 'AgentB',
      actionSummary: '发送心跳信令',
      payloadSnippet: '{"ping": true}',
      tokenCost: 20,
      latencyMs: 15,
      status: 'in_progress',
    });

    expect(id).toBeDefined();
    const store = useAmbientActivityStore.getState();
    const item = store.activities[id];
    expect(item).toBeDefined();
    expect(item?.sourceAgent).toBe('AgentA');
    expect(item?.status).toBe('in_progress');
  });

  it('updates activity status and fields', () => {
    const id = useAmbientActivityStore.getState().recordActivity({
      id: 'custom-act-id',
      sessionId: 'sess-200',
      sourceAgent: 'Planner',
      targetAgent: 'Executor',
      actionSummary: '生成执行计划',
      payloadSnippet: '{"step": 1}',
      tokenCost: 100,
      latencyMs: 50,
      status: 'in_progress',
    });

    useAmbientActivityStore
      .getState()
      .updateActivityStatus('custom-act-id', 'completed', {
        latencyMs: 85,
        tokenCost: 120,
      });

    const updated =
      useAmbientActivityStore.getState().activities['custom-act-id'];
    expect(updated?.status).toBe('completed');
    expect(updated?.latencyMs).toBe(85);
    expect(updated?.tokenCost).toBe(120);
  });

  it('toggles inspection drawer and selected activity', () => {
    useAmbientActivityStore.getState().toggleInspectionDrawer(true);
    expect(useAmbientActivityStore.getState().isInspectionDrawerOpen).toBe(true);

    useAmbientActivityStore.getState().setSelectedActivity('act-target-99');
    expect(useAmbientActivityStore.getState().selectedActivityId).toBe(
      'act-target-99',
    );

    useAmbientActivityStore.getState().toggleInspectionDrawer(false);
    expect(useAmbientActivityStore.getState().isInspectionDrawerOpen).toBe(
      false,
    );
  });

  it('toggles deck collapse and sidebar visibility flags', () => {
    useAmbientActivityStore.getState().toggleDeckCollapse(true);
    expect(useAmbientActivityStore.getState().isDeckCollapsed).toBe(true);

    useAmbientActivityStore.getState().toggleDeckCollapse();
    expect(useAmbientActivityStore.getState().isDeckCollapsed).toBe(false);

    useAmbientActivityStore.getState().toggleShowHiddenBots(true);
    expect(useAmbientActivityStore.getState().showHiddenBotsInSidebar).toBe(
      true,
    );
  });

  it('calculates deck summary from recorded activities', () => {
    useAmbientActivityStore.getState().recordActivity({
      sessionId: 's-1',
      sourceAgent: 'Alpha',
      targetAgent: 'Beta',
      actionSummary: '动作1',
      payloadSnippet: '',
      tokenCost: 50,
      latencyMs: 10,
      status: 'completed',
    });
    useAmbientActivityStore.getState().recordActivity({
      sessionId: 's-1',
      sourceAgent: 'Beta',
      targetAgent: 'Gamma',
      actionSummary: '动作2',
      payloadSnippet: '',
      tokenCost: 75,
      latencyMs: 15,
      status: 'completed',
    });

    const summary = useAmbientActivityStore.getState().getDeckSummary();
    expect(summary.activeAgentsCount).toBe(3); // Alpha, Beta, Gamma
    expect(summary.totalExchangesCount).toBe(2);
    expect(summary.totalTokenCost).toBe(125);
  });

  it('clears and resets store properly', () => {
    useAmbientActivityStore.getState().recordActivity({
      sessionId: 's-clear',
      sourceAgent: 'A',
      targetAgent: 'B',
      actionSummary: 'test',
      payloadSnippet: '',
      tokenCost: 10,
      latencyMs: 5,
      status: 'completed',
    });
    useAmbientActivityStore.getState().setSelectedActivity('s-clear');
    useAmbientActivityStore.getState().toggleInspectionDrawer(true);

    useAmbientActivityStore.getState().clear();
    expect(useAmbientActivityStore.getState().activities).toEqual({});
    expect(useAmbientActivityStore.getState().selectedActivityId).toBeNull();
    // clear 保留抽屉开关
    expect(useAmbientActivityStore.getState().isInspectionDrawerOpen).toBe(true);

    useAmbientActivityStore.getState().reset();
    expect(useAmbientActivityStore.getState().isInspectionDrawerOpen).toBe(
      false,
    );
  });
});
