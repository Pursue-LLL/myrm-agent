import { describe, it, expect, beforeEach } from 'vitest';
import { useSkeuomorphicAppStore } from '../useSkeuomorphicAppStore';

describe('useSkeuomorphicAppStore', () => {
  beforeEach(() => {
    useSkeuomorphicAppStore.getState().resetStore();
  });

  it('初始状态应具备默认的 iPod 皮肤与初始工件数据', () => {
    const state = useSkeuomorphicAppStore.getState();
    expect(state.activeSkin).toBe('classic_ipod');
    expect(state.artifacts.length).toBeGreaterThan(0);
    expect(state.activeItemIndex).toBe(0);
    expect(state.isDetailOpen).toBe(false);
    expect(state.soundEnabled).toBe(true);
    expect(state.hapticEnabled).toBe(true);
  });

  it('setActiveSkin 应正确切换拟物化皮肤', () => {
    useSkeuomorphicAppStore.getState().setActiveSkin('polaroid_album');
    expect(useSkeuomorphicAppStore.getState().activeSkin).toBe('polaroid_album');
  });

  it('nextItem 与 prevItem 应正确循环回绕工件序列', () => {
    const total = useSkeuomorphicAppStore.getState().artifacts.length;
    expect(total).toBeGreaterThan(1);

    useSkeuomorphicAppStore.getState().nextItem();
    expect(useSkeuomorphicAppStore.getState().activeItemIndex).toBe(1);

    useSkeuomorphicAppStore.getState().prevItem();
    expect(useSkeuomorphicAppStore.getState().activeItemIndex).toBe(0);

    // 逆时针跳到最后一项
    useSkeuomorphicAppStore.getState().prevItem();
    expect(useSkeuomorphicAppStore.getState().activeItemIndex).toBe(total - 1);
  });

  it('openDetailModal 与 closeDetailModal 应正确控制工件成果详情视窗', () => {
    useSkeuomorphicAppStore.getState().openDetailModal();
    expect(useSkeuomorphicAppStore.getState().isDetailOpen).toBe(true);

    useSkeuomorphicAppStore.getState().closeDetailModal();
    expect(useSkeuomorphicAppStore.getState().isDetailOpen).toBe(false);
  });

  it('音效、震动、自动播放与最小化开关应正确响应', () => {
    useSkeuomorphicAppStore.getState().toggleSound();
    expect(useSkeuomorphicAppStore.getState().soundEnabled).toBe(false);

    useSkeuomorphicAppStore.getState().toggleHaptic();
    expect(useSkeuomorphicAppStore.getState().hapticEnabled).toBe(false);

    useSkeuomorphicAppStore.getState().toggleAutoPlay();
    expect(useSkeuomorphicAppStore.getState().autoPlay).toBe(true);

    useSkeuomorphicAppStore.getState().toggleMinimized();
    expect(useSkeuomorphicAppStore.getState().isMinimized).toBe(true);
  });
});
