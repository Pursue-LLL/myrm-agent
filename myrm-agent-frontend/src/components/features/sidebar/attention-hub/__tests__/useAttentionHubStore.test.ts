import { describe, it, expect, beforeEach, vi } from 'vitest';
import { act } from '@testing-library/react';
import type { AttentionItem } from '../attentionHubTypes';
import { useAttentionHubStore } from '../useAttentionHubStore';

describe('useAttentionHubStore', () => {
  beforeEach(() => {
    act(() => {
      useAttentionHubStore.getState().resetStore();
    });
  });

  const mockItem1: AttentionItem = {
    id: 'item_1',
    chatId: 'chat_alpha',
    chatTitle: '会话 Alpha',
    category: 'approval_blocking',
    priority: 'urgent',
    title: '文件写权限审批',
    description: '请求写权限',
    timestamp: 1000,
    isRead: false,
    actionRequired: true,
    targetAnchorNodeId: 'node_alpha',
  };

  const mockItem2: AttentionItem = {
    id: 'item_2',
    chatId: 'chat_beta',
    chatTitle: '会话 Beta',
    category: 'task_completed',
    priority: 'info',
    title: '任务完成',
    description: '数据分析完成',
    timestamp: 2000,
    isRead: false,
    actionRequired: false,
  };

  it('initializes with default state', () => {
    const state = useAttentionHubStore.getState();
    expect(state.items).toEqual([]);
    expect(state.isPanelOpen).toBe(false);
    expect(state.filter.category).toBe('all');
    expect(state.filter.onlyActionRequired).toBe(false);
    expect(state.filter.searchQuery).toBe('');
  });

  it('upserts and updates attention items', () => {
    act(() => {
      useAttentionHubStore.getState().upsertItem(mockItem1);
    });
    expect(useAttentionHubStore.getState().items.length).toBe(1);

    // Update the same item
    const updated: AttentionItem = { ...mockItem1, title: '更新后的审批' };
    act(() => {
      useAttentionHubStore.getState().upsertItem(updated);
    });
    expect(useAttentionHubStore.getState().items.length).toBe(1);
    expect(useAttentionHubStore.getState().items[0].title).toBe('更新后的审批');
  });

  it('removes item by ID', () => {
    act(() => {
      useAttentionHubStore.getState().upsertItem(mockItem1);
      useAttentionHubStore.getState().upsertItem(mockItem2);
    });
    expect(useAttentionHubStore.getState().items.length).toBe(2);

    act(() => {
      useAttentionHubStore.getState().removeItem('item_1');
    });
    expect(useAttentionHubStore.getState().items.length).toBe(1);
    expect(useAttentionHubStore.getState().items[0].id).toBe('item_2');
  });

  it('marks single and all items as read', () => {
    act(() => {
      useAttentionHubStore.getState().upsertItem(mockItem1);
      useAttentionHubStore.getState().upsertItem(mockItem2);
    });

    act(() => {
      useAttentionHubStore.getState().markAsRead('item_1');
    });
    expect(useAttentionHubStore.getState().items.find((i) => i.id === 'item_1')?.isRead).toBe(true);
    expect(useAttentionHubStore.getState().items.find((i) => i.id === 'item_2')?.isRead).toBe(false);

    act(() => {
      useAttentionHubStore.getState().markAllAsRead();
    });
    expect(useAttentionHubStore.getState().items.every((i) => i.isRead)).toBe(true);
  });

  it('clears resolved non-blocking items via batchClearResolved', () => {
    act(() => {
      useAttentionHubStore.getState().upsertItem(mockItem1); // actionRequired: true
      useAttentionHubStore.getState().upsertItem(mockItem2); // actionRequired: false
    });

    act(() => {
      useAttentionHubStore.getState().batchClearResolved();
    });
    const remaining = useAttentionHubStore.getState().items;
    expect(remaining.length).toBe(1);
    expect(remaining[0].id).toBe('item_1');
  });

  it('toggles panel visibility', () => {
    expect(useAttentionHubStore.getState().isPanelOpen).toBe(false);

    act(() => {
      useAttentionHubStore.getState().togglePanel();
    });
    expect(useAttentionHubStore.getState().isPanelOpen).toBe(true);

    act(() => {
      useAttentionHubStore.getState().togglePanel(false);
    });
    expect(useAttentionHubStore.getState().isPanelOpen).toBe(false);
  });

  it('updates filters properly', () => {
    act(() => {
      useAttentionHubStore.getState().setCategoryFilter('approval_blocking');
      useAttentionHubStore.getState().setSearchQuery('权限');
      useAttentionHubStore.getState().setOnlyActionRequired(true);
    });

    const filter = useAttentionHubStore.getState().filter;
    expect(filter.category).toBe('approval_blocking');
    expect(filter.searchQuery).toBe('权限');
    expect(filter.onlyActionRequired).toBe(true);
  });

  it('shuttles to target, marks as read, and calls navigation callback', () => {
    const onNav = vi.fn();
    act(() => {
      useAttentionHubStore.getState().upsertItem(mockItem1);
    });

    // Create target DOM node to simulate anchor in the DOM
    const el = document.createElement('div');
    el.id = 'node_alpha';
    const scrollMock = vi.fn();
    Object.defineProperty(el, 'scrollIntoView', {
      value: scrollMock,
      writable: true,
      configurable: true,
    });
    document.body.appendChild(el);

    let result = false;
    act(() => {
      result = useAttentionHubStore.getState().shuttleToTarget('item_1', onNav);
    });

    expect(result).toBe(true);
    expect(onNav).toHaveBeenCalledWith('chat_alpha');
    expect(useAttentionHubStore.getState().items[0].isRead).toBe(true);
    expect(scrollMock).toHaveBeenCalled();

    document.body.removeChild(el);
  });
});
