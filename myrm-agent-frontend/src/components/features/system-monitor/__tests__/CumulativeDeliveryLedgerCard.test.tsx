import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { CumulativeDeliveryLedgerCard } from '../CumulativeDeliveryLedgerCard';
import { TrialLedgerBreakdownTable } from '../TrialLedgerBreakdownTable';
import type { CumulativeDeliveryLedgerData } from '../deliveryBudgetTypes';

describe('CumulativeDeliveryLedgerCard & TrialLedgerBreakdownTable', () => {
  const mockNormalLedger: CumulativeDeliveryLedgerData = {
    delivery_id: 'deliv-web-audit-01',
    title: '全自动合规报告编制流水线',
    budget_tokens_limit: 100000,
    budget_cost_limit_usd: 1.0,
    total_metered_tokens: 32000,
    total_imputed_tokens: 0,
    total_effective_tokens: 32000,
    total_metered_cost_usd: 0.16,
    total_imputed_cost_usd: 0.0,
    total_effective_cost_usd: 0.16,
    unmetered_trials_count: 0,
    total_trials_count: 3,
    gate_verdict: 'NORMAL',
    is_paused: false,
    pause_reason: null,
    trials: [
      {
        trial_id: 'trial-01',
        agent_id: 'planner-01',
        agent_role: 'planner',
        attempt_index: 1,
        step_name: '拆解合规条目清单',
        prompt_tokens: 10000,
        completion_tokens: 2000,
        total_tokens: 12000,
        cost_usd: 0.06,
        latency_ms: 1800,
        is_unmetered: false,
        unmetered_status: 'METERED',
        imputed_prompt_tokens: 0,
        imputed_completion_tokens: 0,
        imputed_cost_usd: 0,
        effective_tokens: 12000,
        effective_cost_usd: 0.06,
        status: 'success',
        created_at: '2026-10-12T10:00:00Z',
      },
    ],
    created_at: '2026-10-12T10:00:00Z',
    updated_at: '2026-10-12T10:05:00Z',
  };

  const mockPausedLedger: CumulativeDeliveryLedgerData = {
    delivery_id: 'deliv-heavy-crawl-02',
    title: '海量财报智能抽取与对账',
    budget_tokens_limit: 50000,
    budget_cost_limit_usd: 0.5,
    total_metered_tokens: 45000,
    total_imputed_tokens: 8000,
    total_effective_tokens: 53000,
    total_metered_cost_usd: 0.45,
    total_imputed_cost_usd: 0.08,
    total_effective_cost_usd: 0.53,
    unmetered_trials_count: 2,
    total_trials_count: 6,
    gate_verdict: 'EXCEEDED_PAUSED_100',
    is_paused: true,
    pause_reason: '已突破单次宏大需求硬预算门禁上限，防止失控多智能体死循环消耗。',
    trials: [
      {
        trial_id: 'trial-c-01',
        agent_id: 'crawler-01',
        agent_role: 'worker',
        attempt_index: 1,
        step_name: '网页抽取解析',
        prompt_tokens: 0,
        completion_tokens: 0,
        total_tokens: 0,
        cost_usd: 0,
        latency_ms: 5000,
        is_unmetered: true,
        unmetered_status: 'UNMETERED_TIMEOUT',
        imputed_prompt_tokens: 3000,
        imputed_completion_tokens: 1000,
        imputed_cost_usd: 0.04,
        effective_tokens: 4000,
        effective_cost_usd: 0.04,
        status: 'timeout',
        created_at: '2026-10-12T11:00:00Z',
      },
    ],
    created_at: '2026-10-12T11:00:00Z',
    updated_at: '2026-10-12T11:20:00Z',
  };

  it('renders normal cumulative ledger card with KPIs and healthy badge', () => {
    render(<CumulativeDeliveryLedgerCard ledger={mockNormalLedger} />);

    expect(screen.getByTestId('cumulative-delivery-ledger-card')).toBeInTheDocument();
    expect(screen.getByText('全自动合规报告编制流水线')).toBeInTheDocument();
    expect(screen.getByText('预算充裕 · 正常推进')).toBeInTheDocument();
    expect(screen.getByText('32,000')).toBeInTheDocument();
    expect(screen.getByText('$0.1600')).toBeInTheDocument();
    expect(screen.getByText('100% 具备精确用量回执')).toBeInTheDocument();
    expect(screen.queryByTestId('budget-fuse-alert-banner')).not.toBeInTheDocument();
  });

  it('renders paused ledger with circuit breaker banner and quick add budget button', async () => {
    const handleAdjust = vi.fn().mockResolvedValue(undefined);
    render(
      <CumulativeDeliveryLedgerCard
        ledger={mockPausedLedger}
        onAdjustBudget={handleAdjust}
      />
    );

    expect(screen.getByText('硬预算熔断 · 保护性挂起')).toBeInTheDocument();
    expect(screen.getByTestId('budget-fuse-alert-banner')).toBeInTheDocument();
    expect(screen.getByTestId('unmetered-alert-count')).toHaveTextContent('包含 2 次未计量计提');

    const addBtn = screen.getByTestId('quick-add-budget-btn');
    fireEvent.click(addBtn);

    expect(handleAdjust).toHaveBeenCalledWith({
      additional_tokens: 50000,
      additional_cost_usd: 0.5,
      force_unpause: true,
    });
  });

  it('toggles trial ledger breakdown table display', () => {
    render(<CumulativeDeliveryLedgerCard ledger={mockNormalLedger} />);

    expect(screen.queryByTestId('trials-breakdown-section')).not.toBeInTheDocument();

    const toggleBtn = screen.getByTestId('toggle-breakdown-btn');
    fireEvent.click(toggleBtn);

    expect(screen.getByTestId('trials-breakdown-section')).toBeInTheDocument();
    expect(screen.getByText('拆解合规条目清单')).toBeInTheDocument();
    expect(screen.getByText('精确计量')).toBeInTheDocument();

    fireEvent.click(toggleBtn);
    expect(screen.queryByTestId('trials-breakdown-section')).not.toBeInTheDocument();
  });

  it('renders unmetered warning tags in TrialLedgerBreakdownTable', () => {
    render(<TrialLedgerBreakdownTable trials={mockPausedLedger.trials} />);

    expect(screen.getByTestId('unmetered-badge-trial-c-01')).toHaveTextContent(
      '⚠️ 未知用量保守计提'
    );
    expect(screen.getByText(/UNMETERED_TIMEOUT/)).toBeInTheDocument();
    expect(screen.getByText('(计提)')).toBeInTheDocument();
  });

  it('renders loading placeholder when ledger is null', () => {
    render(<CumulativeDeliveryLedgerCard ledger={null} />);
    expect(screen.getByTestId('delivery-ledger-loading')).toBeInTheDocument();
  });

  it('renders empty placeholder when trials list is empty', () => {
    render(<TrialLedgerBreakdownTable trials={[]} />);
    expect(screen.getByTestId('trial-breakdown-empty')).toBeInTheDocument();
  });
});
