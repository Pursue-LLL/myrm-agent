import React from 'react';
import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import { useActivityFeedStore } from '../useActivityFeedStore';
import { ActivityFeedAggregatorDeck } from '../ActivityFeedAggregatorDeck';
import type { ActivityFeedItem } from '../activityFeedTypes';

describe('ActivityFeedAggregatorDeck', () => {
  beforeEach(() => {
    act(() => {
      useActivityFeedStore.getState().resetStore();
    });
  });

  const mockItem1: ActivityFeedItem = {
    id: 'deck_1',
    sourceSystem: 'email',
    sourceRefId: 'em_100',
    title: '客户法务邮件初审',
    summary: '已自动识别签字条款',
    autonomyTier: 'full_autonomous',
    status: 'pending_decision',
    timestamp: 1000,
    priority: 'normal',
  };

  const mockItem2: ActivityFeedItem = {
    id: 'deck_2',
    sourceSystem: 'approval',
    sourceRefId: 'apr_200',
    title: '生产环境部署放行',
    summary: '发布 v3.0 镜像到生产集群',
    autonomyTier: 'human_decision_required',
    status: 'pending_decision',
    timestamp: 2000,
    priority: 'urgent',
  };

  it('renders empty state when there are no feed items', () => {
    render(<ActivityFeedAggregatorDeck />);
    expect(screen.getByRole('region', { name: '多系统事项聚合活动流' })).toBeInTheDocument();
    expect(screen.getByText('暂无聚合事项，多系统自治平稳运行')).toBeInTheDocument();
  });

  it('renders items list with header and controls', () => {
    act(() => {
      useActivityFeedStore.getState().ingestItem(mockItem1);
      useActivityFeedStore.getState().ingestItem(mockItem2);
    });

    render(<ActivityFeedAggregatorDeck />);
    expect(screen.getByText('事项聚合活动流')).toBeInTheDocument();
    expect(screen.getByText('客户法务邮件初审')).toBeInTheDocument();
    expect(screen.getByText('生产环境部署放行')).toBeInTheDocument();
  });

  it('toggles pause and resume auto evaporation', () => {
    render(<ActivityFeedAggregatorDeck />);
    const pauseBtn = screen.getByRole('button', { name: /暂停蒸发/ });
    expect(pauseBtn).toBeInTheDocument();

    fireEvent.click(pauseBtn);
    expect(useActivityFeedStore.getState().isEvaporationPaused).toBe(true);
    expect(screen.getByRole('button', { name: /恢复自动蒸发/ })).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /恢复自动蒸发/ }));
    expect(useActivityFeedStore.getState().isEvaporationPaused).toBe(false);
  });

  it('filters by source system tab', () => {
    act(() => {
      useActivityFeedStore.getState().ingestItem(mockItem1);
      useActivityFeedStore.getState().ingestItem(mockItem2);
    });

    render(<ActivityFeedAggregatorDeck />);

    // Click '审批' tab
    const approvalTab = screen.getByRole('button', { name: '审批' });
    fireEvent.click(approvalTab);

    expect(screen.getByText('生产环境部署放行')).toBeInTheDocument();
    expect(screen.queryByText('客户法务邮件初审')).not.toBeInTheDocument();

    // Click '全源汇总' tab
    const allTab = screen.getByRole('button', { name: '全源汇总' });
    fireEvent.click(allTab);

    expect(screen.getByText('生产环境部署放行')).toBeInTheDocument();
    expect(screen.getByText('客户法务邮件初审')).toBeInTheDocument();
  });

  it('filters by search input query', () => {
    act(() => {
      useActivityFeedStore.getState().ingestItem(mockItem1);
      useActivityFeedStore.getState().ingestItem(mockItem2);
    });

    render(<ActivityFeedAggregatorDeck />);

    const searchInput = screen.getByRole('textbox', { name: '搜索活动流事件' });
    fireEvent.change(searchInput, { target: { value: '法务' } });

    expect(screen.getByText('客户法务邮件初审')).toBeInTheDocument();
    expect(screen.queryByText('生产环境部署放行')).not.toBeInTheDocument();
  });

  it('filters by onlyHumanRequired toggle checkbox', () => {
    act(() => {
      useActivityFeedStore.getState().ingestItem(mockItem1);
      useActivityFeedStore.getState().ingestItem(mockItem2);
    });

    render(<ActivityFeedAggregatorDeck />);

    const checkbox = screen.getByRole('checkbox', { name: /只看待你拍板/ });
    fireEvent.click(checkbox);

    expect(screen.getByText('生产环境部署放行')).toBeInTheDocument();
    expect(screen.queryByText('客户法务邮件初审')).not.toBeInTheDocument();
  });

  it('opens evaporated archive drawer and allows undoing evaporation', () => {
    act(() => {
      useActivityFeedStore.getState().ingestItem(mockItem1);
      useActivityFeedStore.getState().evaporateItem('deck_1');
    });

    render(<ActivityFeedAggregatorDeck />);

    const archiveBtn = screen.getByRole('button', { name: /已蒸发备查/ });
    fireEvent.click(archiveBtn);

    // Dialog is open
    expect(screen.getByRole('dialog')).toBeInTheDocument();
    expect(screen.getByText(/已自动蒸发归档备查/)).toBeInTheDocument();

    // Find undo button and click
    const undoBtn = screen.getByRole('button', { name: /撤销蒸发/ });
    fireEvent.click(undoBtn);

    expect(useActivityFeedStore.getState().archive.length).toBe(0);
    expect(useActivityFeedStore.getState().items.length).toBe(1);
    expect(useActivityFeedStore.getState().items[0].id).toBe('deck_1');
  });
});
