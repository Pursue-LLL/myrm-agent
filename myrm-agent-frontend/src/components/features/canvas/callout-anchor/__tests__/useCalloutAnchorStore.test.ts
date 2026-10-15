import { describe, it, expect, beforeEach, vi } from 'vitest';
import { useCalloutAnchorStore } from '../useCalloutAnchorStore';

describe('useCalloutAnchorStore', () => {
  beforeEach(() => {
    useCalloutAnchorStore.getState().resetToDefault();
    vi.restoreAllMocks();
  });

  it('初始状态具备默认锚点与预设激活项', () => {
    const state = useCalloutAnchorStore.getState();
    expect(state.anchors.length).toBeGreaterThanOrEqual(4);
    expect(state.activeAnchorId).toBe('anchor-truss-heel-01');

    const active = state.getActiveAnchor();
    expect(active?.id).toBe('anchor-truss-heel-01');
    expect(active?.label).toContain('桁架根部支座节点');
  });

  it('focusAnchor 能够更新聚焦锚点、计算居中矩阵并派发全局事件', () => {
    const dispatchSpy = vi.spyOn(window, 'dispatchEvent');
    const { focusAnchor } = useCalloutAnchorStore.getState();

    focusAnchor('anchor-db-pool-02', 'chip');

    const state = useCalloutAnchorStore.getState();
    expect(state.activeAnchorId).toBe('anchor-db-pool-02');
    expect(state.isPulseAnimating).toBe(true);
    expect(state.viewportTransform.scale).toBeGreaterThan(0);

    expect(dispatchSpy).toHaveBeenCalled();
  });

  it('setHoveredAnchorId 能够更新悬停预览目标', () => {
    const { setHoveredAnchorId } = useCalloutAnchorStore.getState();
    setHoveredAnchorId('anchor-pay-btn-03');

    expect(useCalloutAnchorStore.getState().hoveredAnchorId).toBe(
      'anchor-pay-btn-03'
    );

    setHoveredAnchorId(null);
    expect(useCalloutAnchorStore.getState().hoveredAnchorId).toBeNull();
  });

  it('setViewportDimensions 更新画布尺寸', () => {
    const { setViewportDimensions } = useCalloutAnchorStore.getState();
    setViewportDimensions(800, 600);

    const dims = useCalloutAnchorStore.getState().viewportDimensions;
    expect(dims.width).toBe(800);
    expect(dims.height).toBe(600);
  });

  it('resetViewport 能够将相机复位为 100% 全貌且清除聚焦态', () => {
    const { resetViewport } = useCalloutAnchorStore.getState();
    resetViewport();

    const state = useCalloutAnchorStore.getState();
    expect(state.viewportTransform).toEqual({
      translateX: 0,
      translateY: 0,
      scale: 1,
    });
    expect(state.activeAnchorId).toBeNull();
    expect(state.isPulseAnimating).toBe(false);
  });
});
