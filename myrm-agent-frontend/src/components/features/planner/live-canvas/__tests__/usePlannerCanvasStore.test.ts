import { describe, it, expect, beforeEach } from 'vitest';
import { usePlannerCanvasStore } from '../usePlannerCanvasStore';

describe('usePlannerCanvasStore', () => {
  beforeEach(() => {
    usePlannerCanvasStore.getState().resetToMockPlanner();
  });

  it('初始状态具备预设模拟任务节点与默认选中的步骤', () => {
    const state = usePlannerCanvasStore.getState();
    expect(state.nodes.length).toBeGreaterThanOrEqual(4);
    expect(state.selectedNodeId).toBe('step-3-codegen');
    expect(state.viewMode).toBe('split');
    expect(state.viewportMode).toBe('desktop');
  });

  it('updateNodeStatus 能够更新节点状态与耗时', () => {
    const { updateNodeStatus } = usePlannerCanvasStore.getState();
    updateNodeStatus('step-4-lint', 'running', 350);

    const updated = usePlannerCanvasStore
      .getState()
      .nodes.find((n) => n.id === 'step-4-lint');
    expect(updated?.status).toBe('running');
    expect(updated?.durationMs).toBe(350);
  });

  it('selectNode 与 getSelectedNode 能够联动定位目标步骤', () => {
    const { selectNode, getSelectedNode } = usePlannerCanvasStore.getState();
    selectNode('step-1-analysis');

    expect(usePlannerCanvasStore.getState().selectedNodeId).toBe('step-1-analysis');
    const selected = getSelectedNode();
    expect(selected?.id).toBe('step-1-analysis');
    expect(selected?.title).toContain('意图拆解');
  });

  it('setViewportMode 与 setViewMode 驱动视口与视图排版切换', () => {
    const { setViewportMode, setViewMode } = usePlannerCanvasStore.getState();

    setViewportMode('mobile');
    expect(usePlannerCanvasStore.getState().viewportMode).toBe('mobile');

    setViewMode('sandbox-only');
    expect(usePlannerCanvasStore.getState().viewMode).toBe('sandbox-only');
  });

  it('triggerSandboxReload 触发重载 key 递增', () => {
    const initialKey = usePlannerCanvasStore.getState().sandboxReloadKey;
    const { triggerSandboxReload } = usePlannerCanvasStore.getState();

    triggerSandboxReload();
    expect(usePlannerCanvasStore.getState().sandboxReloadKey).toBe(initialKey + 1);
  });

  it('getActiveArtifact 优先提取选中节点的交付物或回退到首个可用产物', () => {
    const { selectNode, getActiveArtifact } = usePlannerCanvasStore.getState();

    // 选中拥有产物的 step-3-codegen
    selectNode('step-3-codegen');
    let artifact = getActiveArtifact();
    expect(artifact).toBeDefined();
    expect(artifact?.title).toContain('实时指标看板组件');

    // 选中无产物的 step-1-analysis 时，应优雅回退至首个包含产物的节点
    selectNode('step-1-analysis');
    artifact = getActiveArtifact();
    expect(artifact).toBeDefined();
    expect(artifact?.artifactId).toBe('art-preview-01');
  });
});
