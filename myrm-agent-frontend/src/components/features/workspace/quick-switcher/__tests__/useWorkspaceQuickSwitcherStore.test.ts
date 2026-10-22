import { describe, it, expect, beforeEach } from 'vitest';
import {
  useWorkspaceQuickSwitcherStore,
  filterWorkspaces,
} from '../useWorkspaceQuickSwitcherStore';

describe('useWorkspaceQuickSwitcherStore', () => {
  beforeEach(() => {
    useWorkspaceQuickSwitcherStore.getState().resetToDefaults();
  });

  it('initializes with default workspaces and valid current workspace', () => {
    const state = useWorkspaceQuickSwitcherStore.getState();
    expect(state.workspaces.length).toBeGreaterThanOrEqual(3);
    expect(state.currentWorkspaceId).toBeTruthy();
    expect(state.isOpen).toBe(false);
  });

  it('opens, closes, and toggles switcher modal', () => {
    const store = useWorkspaceQuickSwitcherStore.getState();
    store.openSwitcher();
    expect(useWorkspaceQuickSwitcherStore.getState().isOpen).toBe(true);

    store.closeSwitcher();
    expect(useWorkspaceQuickSwitcherStore.getState().isOpen).toBe(false);

    store.toggleSwitcher();
    expect(useWorkspaceQuickSwitcherStore.getState().isOpen).toBe(true);

    store.toggleSwitcher();
    expect(useWorkspaceQuickSwitcherStore.getState().isOpen).toBe(false);
  });

  it('filters workspaces by query across name, path, branch, and rules', () => {
    const workspaces = useWorkspaceQuickSwitcherStore.getState().workspaces;

    const byName = filterWorkspaces(workspaces, 'frontend', 'all');
    expect(byName.some((w) => w.name === 'myrm-agent-frontend')).toBe(true);

    const byPath = filterWorkspaces(workspaces, 'open-perplexity', 'all');
    expect(byPath.length).toBeGreaterThanOrEqual(1);

    const byBranch = filterWorkspaces(workspaces, 'feat/quick-switcher', 'all');
    expect(byBranch.length).toBe(1);

    const byRule = filterWorkspaces(workspaces, 'FASTAPI', 'all');
    expect(byRule.some((w) => w.name === 'myrm-agent-server')).toBe(true);
  });

  it('filters workspaces by tab (favorites and recent)', () => {
    const workspaces = useWorkspaceQuickSwitcherStore.getState().workspaces;
    const favorites = filterWorkspaces(workspaces, '', 'favorites');
    expect(favorites.every((w) => w.isFavorite)).toBe(true);

    const recent = filterWorkspaces(workspaces, '', 'recent');
    expect(recent[0]?.lastOpenedAt).toBeGreaterThanOrEqual(recent[recent.length - 1]?.lastOpenedAt ?? 0);
  });

  it('navigates through items with selectNext and selectPrevious', () => {
    const store = useWorkspaceQuickSwitcherStore.getState();
    expect(store.selectedIndex).toBe(0);

    store.selectNext();
    expect(useWorkspaceQuickSwitcherStore.getState().selectedIndex).toBe(1);

    store.selectPrevious();
    expect(useWorkspaceQuickSwitcherStore.getState().selectedIndex).toBe(0);

    store.selectPrevious();
    const len = store.workspaces.length;
    expect(useWorkspaceQuickSwitcherStore.getState().selectedIndex).toBe(len - 1);
  });

  it('toggles favorite status of workspace', () => {
    const store = useWorkspaceQuickSwitcherStore.getState();
    const ws = store.workspaces[0];
    if (!ws) {
      return;
    }
    const initialFavorite = ws.isFavorite;

    store.toggleFavorite(ws.id);
    const updated = useWorkspaceQuickSwitcherStore
      .getState()
      .workspaces.find((w) => w.id === ws.id);
    expect(updated?.isFavorite).toBe(!initialFavorite);
  });

  it('switches current workspace and dispatches switch event', () => {
    const store = useWorkspaceQuickSwitcherStore.getState();
    const targetWs = store.workspaces[1];
    if (!targetWs) {
      return;
    }

    const switched = store.switchWorkspace(targetWs.id, false);
    expect(switched?.id).toBe(targetWs.id);

    const state = useWorkspaceQuickSwitcherStore.getState();
    expect(state.currentWorkspaceId).toBe(targetWs.id);
    expect(state.lastSwitchEvent?.currentWorkspaceId).toBe(targetWs.id);
    expect(state.isOpen).toBe(false);
  });

  it('adds and removes a workspace', () => {
    const store = useWorkspaceQuickSwitcherStore.getState();
    const initialCount = store.workspaces.length;

    const created = store.addWorkspace({
      id: 'ws-test-project',
      name: 'test-project',
      path: '/path/to/test-project',
      gitBranch: 'develop',
    });

    const stateAfterAdd = useWorkspaceQuickSwitcherStore.getState();
    expect(stateAfterAdd.workspaces.length).toBe(initialCount + 1);
    expect(stateAfterAdd.currentWorkspaceId).toBe(created.id);

    store.removeWorkspace(created.id);
    const stateAfterRemove = useWorkspaceQuickSwitcherStore.getState();
    expect(stateAfterRemove.workspaces.some((w) => w.id === created.id)).toBe(false);
  });
});
