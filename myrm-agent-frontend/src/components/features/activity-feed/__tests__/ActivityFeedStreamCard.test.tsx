import React from 'react';
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import { useActivityFeedStore } from '../useActivityFeedStore';
import { ActivityFeedStreamCard } from '../ActivityFeedStreamCard';
import type { ActivityFeedItem } from '../activityFeedTypes';

describe('ActivityFeedStreamCard', () => {
  beforeEach(() => {
    act(() => {
      useActivityFeedStore.getState().resetStore();
    });
  });

  const humanItem: ActivityFeedItem = {
    id: 'act_human',
    sourceSystem: 'approval',
    sourceRefId: 'apr_909',
    title: '高风险代码合并审批',
    summary: 'PR #142 涉及核心安全认证模块修改',
    autonomyTier: 'human_decision_required',
    status: 'pending_decision',
    timestamp: 1000,
    priority: 'urgent',
    payloadSnippet: 'git diff auth/tokens.py',
  };

  const autonomousItem: ActivityFeedItem = {
    id: 'act_auto',
    sourceSystem: 'cron',
    sourceRefId: 'cr_10',
    title: '夜间数据库健康对账',
    summary: '执行定时一致性巡检',
    autonomyTier: 'full_autonomous',
    status: 'autonomous_processing',
    timestamp: 2000,
    priority: 'normal',
  };

  it('renders human decision blocking card with approve and reject actions', () => {
    const onApprove = vi.fn();
    const onReject = vi.fn();

    render(
      <ActivityFeedStreamCard
        item={humanItem}
        onApprove={onApprove}
        onReject={onReject}
      />,
    );

    expect(screen.getByText('高风险代码合并审批')).toBeInTheDocument();
    expect(screen.getByText('审批决断')).toBeInTheDocument();
    expect(screen.getByText('待你拍板')).toBeInTheDocument();
    expect(screen.getByText('#apr_909')).toBeInTheDocument();
    expect(screen.getByText('git diff auth/tokens.py')).toBeInTheDocument();

    const approveBtn = screen.getByRole('button', { name: /确认放行/ });
    const rejectBtn = screen.getByRole('button', { name: /驳回/ });

    fireEvent.click(approveBtn);
    expect(onApprove).toHaveBeenCalledWith('act_human');

    fireEvent.click(rejectBtn);
    expect(onReject).toHaveBeenCalledWith('act_human');
  });

  it('renders autonomous processing status badge', () => {
    render(<ActivityFeedStreamCard item={autonomousItem} />);
    expect(screen.getByText('夜间数据库健康对账')).toBeInTheDocument();
    expect(screen.getByText('定时调度')).toBeInTheDocument();
    expect(screen.getByText('Agent 自治推进中')).toBeInTheDocument();
  });

  describe('evaporating behavior', () => {
    beforeEach(() => {
      vi.useFakeTimers();
    });

    afterEach(() => {
      vi.useRealTimers();
    });

    it('renders progress bar and auto evaporates when time expires', () => {
      const evaporatingItem: ActivityFeedItem = {
        id: 'act_evap',
        sourceSystem: 'email',
        sourceRefId: 'em_12',
        title: '已归档邮件通知',
        summary: '邮件归档已完成',
        autonomyTier: 'full_autonomous',
        status: 'evaporating',
        timestamp: 1000,
        resolvedAt: Date.now(),
        evaporationTtlMs: 500,
        priority: 'low',
      };

      act(() => {
        useActivityFeedStore.getState().ingestItem(evaporatingItem);
      });

      render(<ActivityFeedStreamCard item={evaporatingItem} />);

      expect(screen.getByText('自主处理完成 · 即将蒸发')).toBeInTheDocument();
      expect(screen.getByRole('progressbar')).toBeInTheDocument();

      // Advance time past evaporation TTL
      act(() => {
        vi.advanceTimersByTime(600);
      });

      // Item should be evaporated and moved to archive
      expect(useActivityFeedStore.getState().items.find((i) => i.id === 'act_evap')).toBeUndefined();
      expect(useActivityFeedStore.getState().archive.find((i) => i.id === 'act_evap')).toBeDefined();
    });
  });
});
