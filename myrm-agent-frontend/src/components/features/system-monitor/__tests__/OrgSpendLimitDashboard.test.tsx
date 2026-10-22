import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { OrgSpendLimitDashboard } from '../OrgSpendLimitDashboard';
import type {
  IdentAttributionItem,
  OrgSpendSummary,
  SpendGovernorDecision,
} from '../orgSpendLimitTypes';

describe('OrgSpendLimitDashboard', () => {
  const mockHealthySummary: OrgSpendSummary = {
    monthly_budget_usd: 100.0,
    current_spend_usd: 45.0,
    remaining_budget_usd: 55.0,
    utilization_pct: 45.0,
    total_records_count: 12,
  };

  const mockTrippedSummary: OrgSpendSummary = {
    monthly_budget_usd: 100.0,
    current_spend_usd: 102.5,
    remaining_budget_usd: 0.0,
    utilization_pct: 102.5,
    total_records_count: 28,
  };

  const mockAttributions: IdentAttributionItem[] = [
    {
      requesting_user_id: 'ident:alice',
      total_calls_count: 8,
      total_tokens: 150000,
      total_spend_usd: 30.0,
      surfaces_breakdown: { CHANNEL: 30.0 },
      primary_surface: 'CHANNEL',
    },
    {
      requesting_user_id: 'ident:bob',
      total_calls_count: 4,
      total_tokens: 75000,
      total_spend_usd: 15.0,
      surfaces_breakdown: { DIRECT_MESSAGE: 15.0 },
      primary_surface: 'DIRECT_MESSAGE',
    },
  ];

  it('renders healthy budget overview, watermarks, and ident attribution table', () => {
    const handleRefresh = vi.fn();
    render(
      <OrgSpendLimitDashboard
        orgId="org_engineering"
        summary={mockHealthySummary}
        attributions={mockAttributions}
        onRefresh={handleRefresh}
      />
    );

    // Title & Org ID
    expect(screen.getByText('Org Shared Spend Governor')).toBeInTheDocument();
    expect(screen.getByText('org_engineering')).toBeInTheDocument();
    expect(screen.getByText('✔ BUDGET HEALTHY')).toBeInTheDocument();

    // Summary Cards
    expect(screen.getByText('$100.00')).toBeInTheDocument();
    expect(screen.getByText('$45.00')).toBeInTheDocument();
    expect(screen.getByText('$55.00')).toBeInTheDocument();
    expect(screen.getByText('45.0%')).toBeInTheDocument();
    expect(screen.getByText(/共计 12 笔调用上报/)).toBeInTheDocument();

    // Attributions Table
    expect(screen.getByText('ident:alice')).toBeInTheDocument();
    expect(screen.getByText('$30.0000')).toBeInTheDocument();
    expect(screen.getByText('ident:bob')).toBeInTheDocument();
    expect(screen.getByText('$15.0000')).toBeInTheDocument();

    // Refresh trigger
    fireEvent.click(screen.getByText('刷新数据'));
    expect(handleRefresh).toHaveBeenCalledTimes(1);
  });

  it('renders circuit breaker alert banner and warning badges when budget exhausted', () => {
    render(
      <OrgSpendLimitDashboard
        orgId="org_finance"
        summary={mockTrippedSummary}
        attributions={mockAttributions}
      />
    );

    // Status badge
    expect(screen.getByText('● CIRCUIT BREAKER TRIPPED')).toBeInTheDocument();

    // Circuit breaker warning banner
    expect(
      screen.getByText(/组织月度 Agent 算力共享预算已 100% 耗尽，硬熔断机制生效中！/)
    ).toBeInTheDocument();
    expect(
      screen.getByText(/群组协同与公共自动化渠道（CHANNEL）已被阻断挂起/)
    ).toBeInTheDocument();
  });

  it('handles simulated pre-check trial and reflects governor decisions', async () => {
    const mockPreCheck = vi.fn().mockResolvedValue({
      action: 'ALLOW',
      current_spend_usd: 45.0,
      monthly_budget_usd: 100.0,
      utilization_pct: 45.0,
      reason: 'Budget capacity healthy.',
      is_blocked: false,
    } as SpendGovernorDecision);

    render(
      <OrgSpendLimitDashboard
        orgId="org_engineering"
        summary={mockHealthySummary}
        attributions={mockAttributions}
        onPreCheck={mockPreCheck}
      />
    );

    const btn = screen.getByText('执行预检决策');
    fireEvent.click(btn);

    await waitFor(() => {
      expect(mockPreCheck).toHaveBeenCalledWith('CHANNEL', 0.5);
      expect(screen.getByText(/决策动作: ALLOW/)).toBeInTheDocument();
      expect(screen.getByText(/Budget capacity healthy/)).toBeInTheDocument();
      expect(screen.getByText(/状态: 放行/)).toBeInTheDocument();
    });
  });

  it('supports local fallback simulation when onPreCheck prop is omitted', async () => {
    render(
      <OrgSpendLimitDashboard
        orgId="org_engineering"
        summary={mockTrippedSummary}
        attributions={mockAttributions}
      />
    );

    const btn = screen.getByText('执行预检决策');
    fireEvent.click(btn);

    await waitFor(() => {
      expect(screen.getByText(/决策动作: CIRCUIT_BREAKER_BLOCKED/)).toBeInTheDocument();
      expect(screen.getByText(/状态: 已阻断挂起/)).toBeInTheDocument();
    });
  });
});
