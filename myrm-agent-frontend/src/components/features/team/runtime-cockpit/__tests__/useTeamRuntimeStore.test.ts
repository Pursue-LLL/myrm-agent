import { describe, it, expect, beforeEach } from 'vitest';
import { useTeamRuntimeStore } from '../useTeamRuntimeStore';

describe('useTeamRuntimeStore', () => {
  beforeEach(() => {
    useTeamRuntimeStore.getState().resetTeamRuntimeState();
  });

  it('initializes with default team nodes and conflicts', () => {
    const state = useTeamRuntimeStore.getState();
    expect(state.nodes.length).toBe(5);
    expect(state.conflicts.length).toBeGreaterThan(0);
    expect(state.selectedNodeId).toBe('node_architect');
    expect(state.telemetry.coordinationHealthScore).toBe(94);
  });

  it('selects node and opens drawer', () => {
    useTeamRuntimeStore.getState().selectNode('node_finance');
    let state = useTeamRuntimeStore.getState();
    expect(state.selectedNodeId).toBe('node_finance');
    expect(state.isDrawerOpen).toBe(true);

    useTeamRuntimeStore.getState().closeDrawer();
    state = useTeamRuntimeStore.getState();
    expect(state.isDrawerOpen).toBe(false);
    expect(state.selectedNodeId).toBeNull();
  });

  it('opens and closes conflict modal', () => {
    useTeamRuntimeStore.getState().openConflictModal('conflict_arch_vs_budget');
    expect(useTeamRuntimeStore.getState().activeConflictId).toBe('conflict_arch_vs_budget');

    useTeamRuntimeStore.getState().closeConflictModal();
    expect(useTeamRuntimeStore.getState().activeConflictId).toBeNull();
  });

  it('updates upstream deliverable and broadcasts stale_prerequisite to downstream nodes', () => {
    const initialBlocked = useTeamRuntimeStore.getState().telemetry.blockedBlindRerunsCount;

    // node_architect 的下游有 node_compliance 与 node_finalizer
    useTeamRuntimeStore.getState().updateNodeDeliverable(
      'node_architect',
      '架构双活方案已优化为同城双中心冷备模式',
      ['优化事实1: 成本压缩至 $32,000']
    );

    const state = useTeamRuntimeStore.getState();
    const architectNode = state.nodes.find((n) => n.id === 'node_architect');
    expect(architectNode?.deliverable?.version).toBe(2);

    // 下游合规与终态节点应变为前提失效
    const complianceNode = state.nodes.find((n) => n.id === 'node_compliance');
    const finalizerNode = state.nodes.find((n) => n.id === 'node_finalizer');
    expect(complianceNode?.status).toBe('stale_prerequisite');
    expect(complianceNode?.staleReason).toContain('上游节点「高可用技术方案」交付物已更新至 v2');
    expect(finalizerNode?.status).toBe('stale_prerequisite');

    // 减负度量大盘指标应相应增加
    expect(state.telemetry.blockedBlindRerunsCount).toBeGreaterThan(initialBlocked);
  });

  it('arbitrates conflict and updates telemetry', () => {
    useTeamRuntimeStore.getState().arbitrateConflict('conflict_arch_vs_budget', 'opt_sla_first');

    const state = useTeamRuntimeStore.getState();
    const conflict = state.conflicts.find((c) => c.id === 'conflict_arch_vs_budget');
    expect(conflict?.status).toBe('resolved');
    expect(conflict?.selectedOptionId).toBe('opt_sla_first');
    expect(conflict?.arbitratedAt).toBeDefined();

    expect(state.telemetry.preventedAlignmentsCount).toBe(5);
    expect(state.telemetry.coordinationHealthScore).toBe(97);
  });
});
