import { describe, it, expect, beforeEach } from 'vitest';
import { useWorkspaceThemingStore } from '../useWorkspaceThemingStore';

describe('useWorkspaceThemingStore', () => {
  beforeEach(() => {
    useWorkspaceThemingStore.getState().reset();
  });

  it('initializes with default coding mode and preset workspaces', () => {
    const state = useWorkspaceThemingStore.getState();
    expect(state.currentMode).toBe('coding');
    expect(state.activeWorkspaceId).toBe('ws-core-dev');
    expect(Object.keys(state.workspaces).length).toBe(3);
    expect(state.isCustomizeThemeModalOpen).toBe(false);
  });

  it('switches current work mode properly', () => {
    const store = useWorkspaceThemingStore.getState();
    store.switchMode('work');
    expect(useWorkspaceThemingStore.getState().currentMode).toBe('work');

    store.switchMode('coding');
    expect(useWorkspaceThemingStore.getState().currentMode).toBe('coding');
  });

  it('sets active workspace and synchronizes currentMode with defaultMode', () => {
    const store = useWorkspaceThemingStore.getState();
    // 切换到市场营销工作区（defaultMode 为 work）
    store.setActiveWorkspace('ws-marketing-q4');

    const state = useWorkspaceThemingStore.getState();
    expect(state.activeWorkspaceId).toBe('ws-marketing-q4');
    expect(state.currentMode).toBe('work');
  });

  it('updates workspace visual theme and timestamp', () => {
    const store = useWorkspaceThemingStore.getState();
    store.updateWorkspaceTheme('ws-core-dev', {
      color: 'emerald',
      icon: 'terminal',
      customLabel: '极客终端',
    });

    const updated =
      useWorkspaceThemingStore.getState().workspaces['ws-core-dev'];
    expect(updated?.theme.color).toBe('emerald');
    expect(updated?.theme.icon).toBe('terminal');
    expect(updated?.theme.customLabel).toBe('极客终端');
  });

  it('manages customize theme modal lifecycle', () => {
    const store = useWorkspaceThemingStore.getState();
    store.openCustomizeThemeModal('ws-core-dev');

    let state = useWorkspaceThemingStore.getState();
    expect(state.isCustomizeThemeModalOpen).toBe(true);
    expect(state.editingWorkspaceId).toBe('ws-core-dev');

    store.closeCustomizeThemeModal();
    state = useWorkspaceThemingStore.getState();
    expect(state.isCustomizeThemeModalOpen).toBe(false);
    expect(state.editingWorkspaceId).toBeNull();
  });
});
