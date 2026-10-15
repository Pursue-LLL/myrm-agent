import React from 'react';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import { useAttentionHubStore } from '../useAttentionHubStore';
import { AttentionHubPanel } from '../AttentionHubPanel';
import type { AttentionItem } from '../attentionHubTypes';

describe('AttentionHubPanel', () => {
  beforeEach(() => {
    act(() => {
      useAttentionHubStore.getState().resetStore();
    });
  });

  const mockItem1: AttentionItem = {
    id: 'item_1',
    chatId: 'chat_alpha',
    chatTitle: '全栈重构工程',
    category: 'approval_blocking',
    priority: 'urgent',
    title: '高危脚本执行审批',
    description: '请求在终端执行 rm -rf 缓存清理命令',
    timestamp: 1000,
    expiresAt: Date.now() + 30000, // 30s remaining
    targetAnchorNodeId: 'node_alpha',
    isRead: false,
    actionRequired: true,
  };

  const mockItem2: AttentionItem = {
    id: 'item_2',
    chatId: 'chat_beta',
    chatTitle: '知识库同步',
    category: 'task_completed',
    priority: 'info',
    title: '向量索引构建完成',
    description: '成功索引 480 个知识块',
    timestamp: 2000,
    isRead: true,
    actionRequired: false,
  };

  it('renders nothing when panel is closed', () => {
    const { container } = render(<AttentionHubPanel />);
    expect(container.firstChild).toBeNull();
  });

  it('renders empty state when panel is open with zero items', () => {
    act(() => {
      useAttentionHubStore.getState().togglePanel(true);
    });

    render(<AttentionHubPanel />);
    expect(screen.getByRole('region', { name: '注意力引导中枢' })).toBeInTheDocument();
    expect(screen.getByText('暂无注意力待办，一切运行正常')).toBeInTheDocument();
  });

  it('renders items list with categories, titles, countdown and shuttle button', () => {
    act(() => {
      useAttentionHubStore.getState().togglePanel(true);
      useAttentionHubStore.getState().upsertItem(mockItem1);
      useAttentionHubStore.getState().upsertItem(mockItem2);
    });

    render(<AttentionHubPanel />);

    expect(screen.getByText('高危脚本执行审批')).toBeInTheDocument();
    expect(screen.getByText('向量索引构建完成')).toBeInTheDocument();
    expect(screen.getAllByText('待审批').length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('任务已完成')).toBeInTheDocument();
    expect(screen.getByText(/秒后超时/)).toBeInTheDocument();
  });

  it('filters items by category tab', () => {
    act(() => {
      useAttentionHubStore.getState().togglePanel(true);
      useAttentionHubStore.getState().upsertItem(mockItem1);
      useAttentionHubStore.getState().upsertItem(mockItem2);
    });

    render(<AttentionHubPanel />);

    // Click '待审批' tab
    const approvalTab = screen.getByRole('button', { name: '待审批' });
    fireEvent.click(approvalTab);

    expect(screen.getByText('高危脚本执行审批')).toBeInTheDocument();
    expect(screen.queryByText('向量索引构建完成')).not.toBeInTheDocument();

    // Click '全部' tab
    const allTab = screen.getByRole('button', { name: '全部' });
    fireEvent.click(allTab);

    expect(screen.getByText('高危脚本执行审批')).toBeInTheDocument();
    expect(screen.getByText('向量索引构建完成')).toBeInTheDocument();
  });

  it('filters items by search query', () => {
    act(() => {
      useAttentionHubStore.getState().togglePanel(true);
      useAttentionHubStore.getState().upsertItem(mockItem1);
      useAttentionHubStore.getState().upsertItem(mockItem2);
    });

    render(<AttentionHubPanel />);

    const searchInput = screen.getByRole('textbox', { name: '搜索注意力条目' });
    fireEvent.change(searchInput, { target: { value: '向量' } });

    expect(screen.queryByText('高危脚本执行审批')).not.toBeInTheDocument();
    expect(screen.getByText('向量索引构建完成')).toBeInTheDocument();
  });

  it('filters items by onlyActionRequired toggle', () => {
    act(() => {
      useAttentionHubStore.getState().togglePanel(true);
      useAttentionHubStore.getState().upsertItem(mockItem1);
      useAttentionHubStore.getState().upsertItem(mockItem2);
    });

    render(<AttentionHubPanel />);

    const checkbox = screen.getByRole('checkbox', { name: /仅显示需处理阻塞/ });
    fireEvent.click(checkbox);

    expect(screen.getByText('高危脚本执行审批')).toBeInTheDocument();
    expect(screen.queryByText('向量索引构建完成')).not.toBeInTheDocument();
  });

  it('triggers batch actions: mark all read, clear resolved, close panel', () => {
    act(() => {
      useAttentionHubStore.getState().togglePanel(true);
      useAttentionHubStore.getState().upsertItem(mockItem1);
      useAttentionHubStore.getState().upsertItem(mockItem2);
    });

    render(<AttentionHubPanel />);

    // Click mark all read
    const markAllReadBtn = screen.getByRole('button', { name: '全部标为已读' });
    fireEvent.click(markAllReadBtn);
    expect(useAttentionHubStore.getState().items.every((i) => i.isRead)).toBe(true);

    // Click clear resolved
    const clearResolvedBtn = screen.getByRole('button', { name: '清理已完成事项' });
    fireEvent.click(clearResolvedBtn);
    expect(useAttentionHubStore.getState().items.length).toBe(1);
    expect(useAttentionHubStore.getState().items[0].id).toBe('item_1');

    // Click close
    const closeBtn = screen.getByRole('button', { name: '关闭面板' });
    fireEvent.click(closeBtn);
    expect(useAttentionHubStore.getState().isPanelOpen).toBe(false);
  });

  it('handles focus shuttle navigation on shuttle button click', () => {
    const onNavigateToChat = vi.fn();
    act(() => {
      useAttentionHubStore.getState().togglePanel(true);
      useAttentionHubStore.getState().upsertItem(mockItem1);
    });

    // Create target anchor node in document
    const el = document.createElement('div');
    el.id = 'node_alpha';
    const scrollMock = vi.fn();
    Object.defineProperty(el, 'scrollIntoView', {
      value: scrollMock,
      writable: true,
      configurable: true,
    });
    document.body.appendChild(el);

    render(<AttentionHubPanel onNavigateToChat={onNavigateToChat} />);

    const shuttleBtn = screen.getByRole('button', { name: /定位穿梭/ });
    fireEvent.click(shuttleBtn);

    expect(onNavigateToChat).toHaveBeenCalledWith('chat_alpha');
    expect(scrollMock).toHaveBeenCalled();

    document.body.removeChild(el);
  });
});
