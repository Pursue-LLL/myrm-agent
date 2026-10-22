import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { RateLimitSourceSplitHUD } from '../RateLimitSourceSplitHUD';
import type { RateLimitSplitMetricsData } from '../rateLimitSplitTypes';

describe('RateLimitSourceSplitHUD', () => {
  const mockData: RateLimitSplitMetricsData = {
    total_requests: 120,
    total_completed: 100,
    total_rate_limited: 15,
    rate_limited_by_source: {
      myrm: 5,
      upstream: 10,
    },
    total_failed: 5,
    failed_by_provider: {
      openai: 2,
      deepseek: 3,
      unknown: 0,
    },
    totals_consistent: true,
    recent_rate_limit_events: [
      {
        source: 'myrm',
        provider: 'openai',
        model: 'gpt-4o',
        timestamp_ms: 1710000001000,
        reason: 'Client concurrency token cap',
      },
      {
        source: 'upstream',
        provider: 'anthropic',
        model: 'claude-3-5-sonnet',
        timestamp_ms: 1710000002000,
        reason: 'HTTP 429 rate limit exceeded',
      },
    ],
    recent_failure_events: [
      {
        provider: 'deepseek',
        model: 'deepseek-r1',
        error_code: 'PROVIDER_503',
        timestamp_ms: 1710000003000,
        reason: 'Server overloaded',
      },
    ],
  };

  it('renders partitioned rate limit metrics, consistency badge, and split ratios', () => {
    const onRefresh = vi.fn();
    const onReset = vi.fn();

    render(
      <RateLimitSourceSplitHUD
        data={mockData}
        onRefresh={onRefresh}
        onReset={onReset}
      />
    );

    // 标题与防扯皮徽标
    expect(
      screen.getByText('限流来源拆分与失败归因 HUD (Rate Limit Source Split)')
    ).toBeInTheDocument();
    expect(screen.getByText('429 归因防扯皮')).toBeInTheDocument();

    // 核心卡片
    expect(screen.getByText('120')).toBeInTheDocument();
    expect(screen.getByText('15')).toBeInTheDocument();
    expect(screen.getByText('5')).toBeInTheDocument();
    expect(screen.getByText('100% 对齐严格一致')).toBeInTheDocument();

    // 拆分与提供商归因
    expect(screen.getByText(/Myrm 本地治理限流/)).toBeInTheDocument();
    expect(screen.getByText(/5 次 \(33.3%\)/)).toBeInTheDocument();
    expect(screen.getByText(/上游厂商拒绝/)).toBeInTheDocument();
    expect(screen.getByText(/10 次 \(66.7%\)/)).toBeInTheDocument();
    expect(screen.getByText('2 失败')).toBeInTheDocument();
    expect(screen.getByText('3 失败')).toBeInTheDocument();
  });

  it('handles tab switching between rate limit events and failure audit logs', () => {
    render(<RateLimitSourceSplitHUD data={mockData} />);

    // 默认展示 429 限流记录
    expect(screen.getByText('Client concurrency token cap')).toBeInTheDocument();
    expect(screen.getByText('HTTP 429 rate limit exceeded')).toBeInTheDocument();

    // 切换到报错记录 tab
    const failureTabBtn = screen.getByText(/最近请求报错记录/);
    fireEvent.click(failureTabBtn);

    expect(screen.getByText('PROVIDER_503')).toBeInTheDocument();
    expect(screen.getByText('Server overloaded')).toBeInTheDocument();
  });

  it('triggers onRefresh and onReset callbacks', async () => {
    const onRefresh = vi.fn();
    const onReset = vi.fn().mockResolvedValue(undefined);

    render(
      <RateLimitSourceSplitHUD
        data={mockData}
        onRefresh={onRefresh}
        onReset={onReset}
      />
    );

    const refreshBtn = screen.getByRole('button', { name: '刷新指标' });
    fireEvent.click(refreshBtn);
    expect(onRefresh).toHaveBeenCalledTimes(1);

    const resetBtn = screen.getByRole('button', { name: '重置计数器' });
    await React.act(async () => {
      fireEvent.click(resetBtn);
    });
    expect(onReset).toHaveBeenCalledTimes(1);
  });

  it('renders drift alert when totals_consistent is false', () => {
    const inconsistentData: RateLimitSplitMetricsData = {
      ...mockData,
      totals_consistent: false,
    };

    render(<RateLimitSourceSplitHUD data={inconsistentData} />);
    expect(screen.getByText('⚠️ 检测到口径漂移')).toBeInTheDocument();
  });
});
