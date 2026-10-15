import React from 'react';
import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import { useAttentionHubStore } from '../useAttentionHubStore';
import { AttentionHubBadge } from '../AttentionHubBadge';
import type { AttentionItem } from '../attentionHubTypes';

describe('AttentionHubBadge', () => {
  beforeEach(() => {
    act(() => {
      useAttentionHubStore.getState().resetStore();
    });
  });

  const normalItem: AttentionItem = {
    id: 'item_1',
    chatId: 'c1',
    chatTitle: 'Chat 1',
    category: 'clarification_needed',
    priority: 'medium',
    title: '参数澄清确认',
    description: '请确认测试环境地址',
    timestamp: 1000,
    isRead: false,
    actionRequired: true,
  };

  const urgentItem: AttentionItem = {
    id: 'item_2',
    chatId: 'c2',
    chatTitle: 'Chat 2',
    category: 'approval_blocking',
    priority: 'urgent',
    title: '删除生产库审批',
    description: '需要高权限确认',
    timestamp: 2000,
    isRead: false,
    actionRequired: true,
  };

  it('renders default idle badge with zero count', () => {
    render(<AttentionHubBadge />);
    const button = screen.getByRole('button', { name: /注意力中枢：0项待处理/ });
    expect(button).toBeInTheDocument();
    expect(screen.getByText('注意力中枢')).toBeInTheDocument();
    // No counter pill is displayed when count is 0
    expect(screen.queryByText('0')).not.toBeInTheDocument();
  });

  it('displays action-required count pill when tasks exist', () => {
    act(() => {
      useAttentionHubStore.getState().upsertItem(normalItem);
    });

    render(<AttentionHubBadge />);
    expect(screen.getByText('1')).toBeInTheDocument();
    const button = screen.getByRole('button', { name: /注意力中枢：1项待处理/ });
    expect(button).toBeInTheDocument();
  });

  it('applies pulse animation when urgent item exists', () => {
    act(() => {
      useAttentionHubStore.getState().upsertItem(urgentItem);
    });

    render(<AttentionHubBadge />);
    const pill = screen.getByText('1');
    expect(pill.className).toContain('animate-pulse');
    expect(pill.className).toContain('bg-rose-500');
  });

  it('toggles panel visibility on click', () => {
    render(<AttentionHubBadge />);
    const button = screen.getByRole('button', { name: /注意力中枢/ });
    expect(button).toHaveAttribute('aria-expanded', 'false');

    fireEvent.click(button);
    expect(useAttentionHubStore.getState().isPanelOpen).toBe(true);

    fireEvent.click(button);
    expect(useAttentionHubStore.getState().isPanelOpen).toBe(false);
  });

  it('hides text in compact mode', () => {
    render(<AttentionHubBadge compact />);
    expect(screen.queryByText('注意力中枢')).not.toBeInTheDocument();
  });
});
