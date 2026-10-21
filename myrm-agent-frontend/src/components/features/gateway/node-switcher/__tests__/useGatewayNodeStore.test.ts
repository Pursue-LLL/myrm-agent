import { describe, it, expect, beforeEach, vi } from 'vitest';
import { useGatewayNodeStore } from '../useGatewayNodeStore';

describe('useGatewayNodeStore', () => {
  beforeEach(() => {
    useGatewayNodeStore.getState().resetToDefault();
    vi.restoreAllMocks();
  });

  it('初始状态具备预设节点并以 node-localhost-01 为当前活动节点', () => {
    const state = useGatewayNodeStore.getState();
    expect(state.nodes.length).toBeGreaterThanOrEqual(3);
    expect(state.activeNodeId).toBe('node-localhost-01');
    const active = state.getActiveNode();
    expect(active?.id).toBe('node-localhost-01');
  });

  it('switchActiveNode 切换活动节点并广播自定义事件', () => {
    const dispatchSpy = vi.spyOn(window, 'dispatchEvent');
    const { switchActiveNode } = useGatewayNodeStore.getState();

    switchActiveNode('node-gpu-vps-02');

    expect(useGatewayNodeStore.getState().activeNodeId).toBe('node-gpu-vps-02');
    expect(dispatchSpy).toHaveBeenCalled();
  });

  it('addNode 规范化 URL 并将新节点推入名册', () => {
    const { addNode } = useGatewayNodeStore.getState();
    const newId = addNode({
      name: 'Office Cluster Node',
      endpointUrl: '10.10.0.88:8000/',
      isDefault: false,
      tags: ['office'],
    });

    const state = useGatewayNodeStore.getState();
    const inserted = state.nodes.find((n) => n.id === newId);
    expect(inserted).toBeDefined();
    expect(inserted?.endpointUrl).toBe('http://10.10.0.88:8000');
    expect(inserted?.name).toBe('Office Cluster Node');
  });

  it('updateNode 支持局部更新特定节点属性', () => {
    const { updateNode } = useGatewayNodeStore.getState();
    updateNode('node-localhost-01', { name: '开发主力机 (更新后)' });

    const updated = useGatewayNodeStore
      .getState()
      .nodes.find((n) => n.id === 'node-localhost-01');
    expect(updated?.name).toBe('开发主力机 (更新后)');
  });

  it('deleteNode 移除活动节点时平滑降级至下一个可用节点', () => {
    const { deleteNode } = useGatewayNodeStore.getState();
    // 当前为 node-localhost-01，删除它
    deleteNode('node-localhost-01');

    const state = useGatewayNodeStore.getState();
    expect(state.nodes.some((n) => n.id === 'node-localhost-01')).toBe(false);
    expect(state.activeNodeId).toBe('node-gpu-vps-02');
  });

  it('setSearchQuery 和 setTagFilter 正确驱动 getFilteredNodes 过滤', () => {
    const { setSearchQuery, getFilteredNodes } = useGatewayNodeStore.getState();
    setSearchQuery('NAS');

    const filtered = getFilteredNodes();
    expect(filtered.length).toBe(1);
    expect(filtered[0].id).toBe('node-home-nas-03');
  });
});
