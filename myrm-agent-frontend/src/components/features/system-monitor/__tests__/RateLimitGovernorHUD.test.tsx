import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { RateLimitGovernorHUD } from '../RateLimitGovernorHUD';
import { SubagentQuotaAllocationDrawer } from '../SubagentQuotaAllocationDrawer';
import type {
  GovernorLiveStatus,
  QuotaPacingDecision,
  SubagentQuotaSlice,
} from '../rateLimitGovernorTypes';

describe('RateLimitGovernorHUD & SubagentQuotaAllocationDrawer', () => {
  const mockStatuses: GovernorLiveStatus[] = [
    {
      model_name: 'claude-3-5-sonnet',
      tpm_watermark_pct: 42.5,
      rpm_watermark_pct: 30.0,
      smoothed_request_count: 3,
      prevented_429_count: 5,
      active_subagent_slices_count: 2,
      status_label: '✓ 绿灯顺畅放行',
    },
    {
      model_name: 'deepseek-chat',
      tpm_watermark_pct: 88.0,
      rpm_watermark_pct: 75.0,
      smoothed_request_count: 12,
      prevented_429_count: 8,
      active_subagent_slices_count: 1,
      status_label: '⚠️ 削峰平流护航',
    },
  ];

  const mockDecision: QuotaPacingDecision = {
    action: 'MICRO_SLEEP_PACED',
    delay_ms: 350,
    current_tpm_usage: 70400,
    max_tpm_limit: 80000,
    tpm_watermark_pct: 88.0,
    current_rpm_usage: 35,
    max_rpm_limit: 50,
    reason: '水位达 88.0% 接近安全预警线，主动施加 350ms 微整形削峰平流。',
    target_model_or_fallback: 'claude-3-5-sonnet',
  };

  const mockSlices: SubagentQuotaSlice[] = [
    {
      workspace_id: 'ws-demo-01',
      subagent_id: 'subagent-crawler',
      allocated_tpm_share: 25000,
      consumed_tokens_in_window: 26000,
      remaining_tokens_in_window: 0,
      is_throttled: true,
    },
    {
      workspace_id: 'ws-demo-01',
      subagent_id: 'subagent-coder',
      allocated_tpm_share: 25000,
      consumed_tokens_in_window: 8000,
      remaining_tokens_in_window: 17000,
      is_throttled: false,
    },
  ];

  it('renders aggregate KPIs and multi-model watermarks in HUD', () => {
    render(
      <RateLimitGovernorHUD
        statuses={mockStatuses}
        latestDecision={null}
      />
    );

    // Header & Badge
    expect(screen.getByText('客户端主动限流预测阀门与自适应配额调度')).toBeInTheDocument();
    expect(screen.getByText('Zero-429 Shield Active')).toBeInTheDocument();

    // Aggregate counts (5 + 8 = 13 prevented, 3 + 12 = 15 smoothed)
    expect(screen.getByText('13')).toBeInTheDocument();
    expect(screen.getByText('15')).toBeInTheDocument();

    // Model names (present in card and dropdown option)
    expect(screen.getAllByText('claude-3-5-sonnet').length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText('deepseek-chat').length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('✓ 绿灯顺畅放行')).toBeInTheDocument();
    expect(screen.getByText('⚠️ 削峰平流护航')).toBeInTheDocument();
  });

  it('triggers simulation pre-check callback with selected model and token count', () => {
    const onTriggerPreCheck = vi.fn();
    render(
      <RateLimitGovernorHUD
        statuses={mockStatuses}
        onTriggerPreCheck={onTriggerPreCheck}
      />
    );

    const simulateBtn = screen.getByRole('button', { name: '执行前置预检' });
    fireEvent.click(simulateBtn);

    expect(onTriggerPreCheck).toHaveBeenCalledTimes(1);
    expect(onTriggerPreCheck).toHaveBeenCalledWith('claude-3-5-sonnet', 2500);
  });

  it('renders latest pre-check decision card with micro-sleep pacing details', () => {
    render(
      <RateLimitGovernorHUD
        statuses={mockStatuses}
        latestDecision={mockDecision}
      />
    );

    expect(screen.getByText('MICRO_SLEEP_PACED')).toBeInTheDocument();
    expect(screen.getByText('350 ms')).toBeInTheDocument();
    expect(screen.getByText(/主动施加 350ms 微整形削峰平流/)).toBeInTheDocument();
  });

  it('triggers open subagent drawer callback when clicked', () => {
    const onOpenDrawer = vi.fn();
    render(
      <RateLimitGovernorHUD
        statuses={mockStatuses}
        onOpenSubagentDrawer={onOpenDrawer}
      />
    );

    const drawerBtn = screen.getByRole('button', { name: /子 Agent 切片配额/ });
    fireEvent.click(drawerBtn);

    expect(onOpenDrawer).toHaveBeenCalledTimes(1);
  });

  it('renders subagent quota allocation drawer with anti-starvation throttling badges and allows reset', () => {
    const onClose = vi.fn();
    const onReset = vi.fn();

    render(
      <SubagentQuotaAllocationDrawer
        isOpen={true}
        workspaceId="ws-demo-01"
        slices={mockSlices}
        onClose={onClose}
        onResetWindow={onReset}
      />
    );

    expect(screen.getByText('子 Agent 隔离配额切片管理')).toBeInTheDocument();
    expect(screen.getByText('subagent-crawler')).toBeInTheDocument();
    expect(screen.getByText('⛔ 切片熔断限流')).toBeInTheDocument();

    expect(screen.getByText('subagent-coder')).toBeInTheDocument();
    expect(screen.getByText('✓ 正常流通')).toBeInTheDocument();

    // Reset window
    const resetBtn = screen.getByRole('button', { name: /一键重置窗口切片/ });
    fireEvent.click(resetBtn);
    expect(onReset).toHaveBeenCalledWith('ws-demo-01');

    // Close
    const closeBtn = screen.getByRole('button', { name: '关闭抽屉' });
    fireEvent.click(closeBtn);
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
