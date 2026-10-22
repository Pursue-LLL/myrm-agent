import { describe, it, expect, beforeEach, vi } from 'vitest';
import { useGlobalCommandHubStore } from '../useGlobalCommandHubStore';

describe('useGlobalCommandHubStore', () => {
  beforeEach(() => {
    useGlobalCommandHubStore.getState().resetState();
  });

  it('initializes with default closed state and default commands registry', () => {
    const state = useGlobalCommandHubStore.getState();

    expect(state.isOpen).toBe(false);
    expect(state.searchQuery).toBe('');
    expect(state.activeCategory).toBe('all');
    expect(state.selectedIndex).toBe(0);
    expect(state.commands.length).toBeGreaterThanOrEqual(10);
    expect(state.recentCommandIds).toContain('ai-code-review');
  });

  it('opens, closes, and toggles command hub visibility', () => {
    const store = useGlobalCommandHubStore.getState();

    store.openHub();
    expect(useGlobalCommandHubStore.getState().isOpen).toBe(true);

    store.closeHub();
    expect(useGlobalCommandHubStore.getState().isOpen).toBe(false);

    store.toggleHub();
    expect(useGlobalCommandHubStore.getState().isOpen).toBe(true);

    store.toggleHub();
    expect(useGlobalCommandHubStore.getState().isOpen).toBe(false);
  });

  it('filters commands by query keywords and categories', () => {
    const store = useGlobalCommandHubStore.getState();

    // 1. 搜索关键词
    store.setSearchQuery('代码审查');
    const queryFiltered = useGlobalCommandHubStore.getState().getFilteredCommands();
    expect(queryFiltered.length).toBeGreaterThan(0);
    expect(queryFiltered[0]?.title).toContain('代码审查');

    // 2. 类别筛选
    store.setSearchQuery('');
    store.setActiveCategory('git');
    const gitFiltered = useGlobalCommandHubStore.getState().getFilteredCommands();
    expect(gitFiltered.every((cmd) => cmd.category === 'git')).toBe(true);

    // 3. 恢复全部
    store.setActiveCategory('all');
    expect(useGlobalCommandHubStore.getState().getFilteredCommands().length).toBeGreaterThanOrEqual(10);
  });

  it('handles cyclic keyboard selection navigation', () => {
    const store = useGlobalCommandHubStore.getState();
    const count = store.getFilteredCommands().length;

    expect(store.selectedIndex).toBe(0);

    // 往下一个
    store.selectNext();
    expect(useGlobalCommandHubStore.getState().selectedIndex).toBe(1);

    // 往上一个（回到0）
    store.selectPrevious();
    expect(useGlobalCommandHubStore.getState().selectedIndex).toBe(0);

    // 往上循环到最后一个
    store.selectPrevious();
    expect(useGlobalCommandHubStore.getState().selectedIndex).toBe(count - 1);
  });

  it('records execution in recent list and executes selected command', () => {
    const mockAction = vi.fn();
    const customCmd = {
      id: 'custom-deploy',
      category: 'action' as const,
      title: '部署到生产环境',
      iconName: 'Zap',
      keywords: ['deploy', '部署'],
      action: mockAction,
    };

    const store = useGlobalCommandHubStore.getState();
    store.registerCommand(customCmd);
    store.openHub();

    // 搜索并选中该命令
    store.setSearchQuery('部署到生产环境');
    const filtered = useGlobalCommandHubStore.getState().getFilteredCommands();
    expect(filtered[0]?.id).toBe('custom-deploy');

    // 执行当前选中
    store.executeSelectedCommand();
    expect(mockAction).toHaveBeenCalledTimes(1);
    expect(useGlobalCommandHubStore.getState().isOpen).toBe(false);
    expect(useGlobalCommandHubStore.getState().recentCommandIds[0]).toBe('custom-deploy');
  });
});
