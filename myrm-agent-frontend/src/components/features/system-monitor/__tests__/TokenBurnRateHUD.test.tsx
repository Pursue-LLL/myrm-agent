import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { TokenBurnRateHUD } from '../TokenBurnRateHUD';
import { BudgetTierAlertBanner } from '../BudgetTierAlertBanner';
import type { WorkflowBurnStatus, BudgetLadderVerdict } from '../types';

describe('TokenBurnRateHUD & BudgetTierAlertBanner', () => {
  const baseStatus: WorkflowBurnStatus = {
    workflow_id: 'wf-batch-1024',
    tokens_per_sec: 1450.5,
    cost_per_hour_usd: 52.2,
    cumulative_prompt_tokens: 35000,
    cumulative_completion_tokens: 15000,
    total_cumulative_tokens: 50000,
    cumulative_cost_usd: 1.8,
    budget_tokens: 100000,
    budget_cost_usd: 5.0,
    active_agent_count: 48,
    agent_burn_distribution: {
      'agent-search-1': 24000,
      'agent-code-2': 16000,
      'agent-eval-3': 10000,
    },
    verdict: {
      workflow_id: 'wf-batch-1024',
      tier: 'NORMAL',
      used_pct: 36.0,
      is_throttled: false,
      is_suspended: false,
      throttle_factor: 1.0,
      action_message: '预算水位充裕（<50%），全速无阻塞并发执行中',
      recommended_model_tier: 'primary',
    },
    updated_at: '2026-10-12T10:00:00Z',
  };

  it('renders tokens per second, hourly cost, and agent distribution', () => {
    render(<TokenBurnRateHUD status={baseStatus} />);

    expect(screen.getByText('海量 Agent 编排 Token 燃速全景 HUD')).toBeInTheDocument();
    expect(screen.getByText(/48 个并发 Agent 运行中/)).toBeInTheDocument();
    expect(screen.getByText(/1,450.5/)).toBeInTheDocument();
    expect(screen.getByText(/\$52.20/)).toBeInTheDocument();
    expect(screen.getByText('50,000')).toBeInTheDocument();
    expect(screen.getByText('agent-search-1')).toBeInTheDocument();
    expect(screen.getByText(/24,000 Tokens/)).toBeInTheDocument();
  });

  it('renders tier 2 degraded alert banner and displays economy model tier', () => {
    const degradedVerdict: BudgetLadderVerdict = {
      workflow_id: 'wf-batch-1024',
      tier: 'TIER2_DEGRADED',
      used_pct: 85.0,
      is_throttled: true,
      is_suspended: false,
      throttle_factor: 0.5,
      action_message: '预算消耗已达 85.0%，触发阶梯二自适应限流降级',
      recommended_model_tier: 'economy',
    };

    render(<BudgetTierAlertBanner verdict={degradedVerdict} />);

    expect(screen.getByText(/阶段二：自适应降级截流生效中/)).toBeInTheDocument();
    expect(screen.getByText(/水位: 85%/)).toBeInTheDocument();
    expect(screen.getByText(/基座: economy/)).toBeInTheDocument();
    expect(screen.getByTestId('quick-add-budget-btn')).toBeInTheDocument();
  });

  it('renders tier 3 suspended banner and triggers budget quick add callback', () => {
    const suspendedStatus: WorkflowBurnStatus = {
      ...baseStatus,
      verdict: {
        workflow_id: 'wf-batch-1024',
        tier: 'TIER3_SUSPENDED',
        used_pct: 105.0,
        is_throttled: true,
        is_suspended: true,
        throttle_factor: 0.0,
        action_message: '已达预设预算上限（105.0%），执行流已触发安全挂起保护',
        recommended_model_tier: 'halted',
      },
    };

    const handleAdjust = vi.fn();
    render(<TokenBurnRateHUD status={suspendedStatus} onAdjustBudget={handleAdjust} />);

    expect(screen.getByText(/阶段三：预算上限硬拦截（执行已安全挂起）/)).toBeInTheDocument();

    const quickAddBtn = screen.getByTestId('quick-add-budget-btn');
    fireEvent.click(quickAddBtn);

    expect(handleAdjust).toHaveBeenCalledWith({
      added_tokens: 50000,
      added_cost_usd: 2.5,
    });
  });
});
