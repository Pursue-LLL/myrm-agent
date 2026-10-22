/**
 * [INPUT]: DurableBudgetLedgerHUD component, mock DurableBudgetRecoverySummaryItem and SessionActualBilledStatementItem.
 * [OUTPUT]: Vitest test suite verifying durable budget recovery, underestimation gap protection, tab switching, and callbacks.
 * [POS]: myrm-agent/myrm-agent-frontend/src/components/features/system-monitor/__tests__/DurableBudgetLedgerHUD.test.tsx
 */

import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { DurableBudgetLedgerHUD } from '../DurableBudgetLedgerHUD';
import {
  DurableBudgetRecoverySummaryItem,
  SessionActualBilledStatementItem,
} from '../durableBudgetLedgerTypes';

describe('DurableBudgetLedgerHUD Component', () => {
  const mockSummaryWithGap: DurableBudgetRecoverySummaryItem = {
    date_utc: '2026-10-13',
    total_durable_cost_usd: 0.075,
    total_surviving_message_cost_usd: 0.040,
    discarded_branch_cost_usd: 0.025,
    records_count: 3,
    category_breakdown: {
      chat: 0.065,
      auxiliary: 0.010,
    },
    budget_underestimation_gap_usd: 0.035,
  };

  const mockStatement: SessionActualBilledStatementItem = {
    session_id: 'sess-hud-001',
    visible_branch_cost_usd: 0.050,
    actual_billed_cost_usd: 0.075,
    discarded_diff_cost_usd: 0.025,
    records: [
      {
        record_id: 'spend-rec-1',
        session_id: 'sess-hud-001',
        task_id: 'task-1',
        cost_usd: 0.050,
        category: 'chat',
        date_utc: '2026-10-13',
        message_id: 'msg-1',
        is_active_branch: true,
        timestamp_ms: 1791800001000,
      },
      {
        record_id: 'spend-rec-2',
        session_id: 'sess-hud-001',
        task_id: 'task-1',
        cost_usd: 0.025,
        category: 'chat',
        date_utc: '2026-10-13',
        message_id: 'msg-rewound-2',
        is_active_branch: false,
        timestamp_ms: 1791800002000,
      },
    ],
  };

  it('renders summary cards and flags underestimation gap accurately', () => {
    render(<DurableBudgetLedgerHUD summary={mockSummaryWithGap} />);

    // Header
    expect(
      screen.getByText(/Durable Daily Budget Recovery & Actual Billed HUD/i)
    ).toBeInTheDocument();

    // Gap Banner
    expect(screen.getByTestId('underestimation-gap-banner')).toBeInTheDocument();
    expect(screen.getByText(/Durable Ledger Reconciled/i)).toBeInTheDocument();

    // Top Cards
    expect(screen.getByTestId('total-durable-cost-val')).toHaveTextContent('$0.0750');
    expect(screen.getByTestId('surviving-msg-cost-val')).toHaveTextContent('$0.0400');
    expect(screen.getByTestId('discarded-branch-cost-val')).toHaveTextContent('$0.0250');
    expect(screen.getByTestId('underestimation-gap-val')).toHaveTextContent('$0.0350');

    // Category breakdown
    expect(screen.getByTestId('cat-card-chat')).toHaveTextContent('$0.0650');
    expect(screen.getByTestId('cat-card-auxiliary')).toHaveTextContent('$0.0100');
  });

  it('handles tab switching and renders session actual billed reconciliation', () => {
    render(<DurableBudgetLedgerHUD summary={mockSummaryWithGap} statement={mockStatement} />);

    // Switch to statement tab
    const tabStatement = screen.getByTestId('tab-statement');
    fireEvent.click(tabStatement);

    // Totals in statement view
    expect(screen.getByTestId('actual-billed-total')).toHaveTextContent('$0.0750');
    expect(screen.getByTestId('visible-branch-total')).toHaveTextContent('$0.0500');
    expect(screen.getByTestId('discarded-diff-total')).toHaveTextContent('$0.0250');

    // Record rows
    expect(screen.getByTestId('statement-row-spend-rec-1')).toBeInTheDocument();
    expect(screen.getByTestId('statement-row-spend-rec-2')).toBeInTheDocument();
    expect(screen.getByText('ACTIVE BRANCH')).toBeInTheDocument();
    expect(screen.getByText('DISCARDED (REWOUND)')).toBeInTheDocument();
  });

  it('handles refresh and reset callbacks correctly', () => {
    const handleRefresh = vi.fn();
    const handleReset = vi.fn();

    render(
      <DurableBudgetLedgerHUD
        summary={mockSummaryWithGap}
        onRefresh={handleRefresh}
        onReset={handleReset}
      />
    );

    const refreshBtn = screen.getByTestId('refresh-budget-ledger-btn');
    fireEvent.click(refreshBtn);
    expect(handleRefresh).toHaveBeenCalledTimes(1);

    const resetBtn = screen.getByTestId('reset-budget-ledger-btn');
    fireEvent.click(resetBtn);
    expect(handleReset).toHaveBeenCalledTimes(1);
  });

  it('renders clean perfect-match banner when gap is zero', () => {
    const perfectSummary: DurableBudgetRecoverySummaryItem = {
      ...mockSummaryWithGap,
      budget_underestimation_gap_usd: 0.0,
      discarded_branch_cost_usd: 0.0,
    };

    render(<DurableBudgetLedgerHUD summary={perfectSummary} />);

    expect(screen.getByTestId('perfect-match-banner')).toBeInTheDocument();
    expect(
      screen.getByText(/Surviving messages match durable ledger perfectly/i)
    ).toBeInTheDocument();
  });
});
