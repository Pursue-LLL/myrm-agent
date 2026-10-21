import { describe, it, expect, beforeEach } from 'vitest';
import { useTurnLineageStore } from '../useTurnLineageStore';

describe('useTurnLineageStore', () => {
  beforeEach(() => {
    useTurnLineageStore.getState().resetStore();
  });

  it('初始状态应具备默认轮次并处于 all 过滤模式', () => {
    const state = useTurnLineageStore.getState();
    expect(state.turns.length).toBeGreaterThanOrEqual(6);
    expect(state.filterMode).toBe('all');
    expect(state.activeTurnId).toBeNull();
    expect(state.highlightedLineageChain).toEqual([]);
    expect(state.isRailExpanded).toBe(true);
  });

  it('setFilterMode 应正确切换审计筛选分类', () => {
    useTurnLineageStore.getState().setFilterMode('automated_only');
    expect(useTurnLineageStore.getState().filterMode).toBe('automated_only');
  });

  it('selectTurn 应正确选中并自动推导因果链路', () => {
    useTurnLineageStore.getState().selectTurn('turn-5');

    const state = useTurnLineageStore.getState();
    expect(state.activeTurnId).toBe('turn-5');
    expect(state.highlightedLineageChain).toEqual(['turn-3', 'turn-4', 'turn-5']);

    // 取消选中
    useTurnLineageStore.getState().selectTurn(null);
    expect(useTurnLineageStore.getState().activeTurnId).toBeNull();
    expect(useTurnLineageStore.getState().highlightedLineageChain).toEqual([]);
  });

  it('toggleRailExpanded 应正确切换时间轴折叠状态', () => {
    useTurnLineageStore.getState().toggleRailExpanded();
    expect(useTurnLineageStore.getState().isRailExpanded).toBe(false);

    useTurnLineageStore.getState().toggleRailExpanded();
    expect(useTurnLineageStore.getState().isRailExpanded).toBe(true);
  });
});
