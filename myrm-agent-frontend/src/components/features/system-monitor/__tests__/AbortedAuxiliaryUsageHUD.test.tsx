/**
 * [INPUT]: AbortedAuxiliaryUsageHUD component, mock AbortedUsageUnknownStatsItem and CanonicalUsageLedgerRowItem.
 * [OUTPUT]: Vitest test suite verifying unknown-usage risk banner, anti-pseudo-free assertions, filtering, and callbacks.
 * [POS]: myrm-agent/myrm-agent-frontend/src/components/features/system-monitor/__tests__/AbortedAuxiliaryUsageHUD.test.tsx
 */

import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { AbortedAuxiliaryUsageHUD } from '../AbortedAuxiliaryUsageHUD';
import {
  AbortedUsageUnknownStatsItem,
  CanonicalUsageLedgerRowItem,
} from '../abortedUsageLedgerTypes';

describe('AbortedAuxiliaryUsageHUD Component', () => {
  const mockStatsWithUnknown: AbortedUsageUnknownStatsItem = {
    total_calls: 3,
    known_usage_calls: 2,
    unknown_usage_calls: 1,
    aborted_calls_count: 1,
    total_known_prompt_tokens: 800,
    total_known_completion_tokens: 400,
    total_known_tokens: 1200,
    total_known_cost_usd: 0.024,
    unknown_risk_flag: true,
    timestamp_ms: 1791800000000,
  };

  const mockRecords: CanonicalUsageLedgerRowItem[] = [
    {
      call_id: 'call-001',
      session_id: 'sess-100',
      task_id: 'task-primary-1',
      call_kind: 'primary',
      call_status: 'completed',
      usage_availability: 'exact',
      prompt_tokens: 500,
      completion_tokens: 300,
      total_tokens: 800,
      cost_usd: 0.016,
      provider_raw_status: 'success',
      timestamp_ms: 1791800001000,
    },
    {
      call_id: 'call-002',
      session_id: 'sess-100',
      task_id: 'task-audit-aborted',
      call_kind: 'auxiliary_audit',
      call_status: 'aborted',
      usage_availability: 'usage-unknown',
      prompt_tokens: null,
      completion_tokens: null,
      total_tokens: null,
      cost_usd: null,
      provider_raw_status: 'client_aborted_early',
      timestamp_ms: 1791800002000,
    },
    {
      call_id: 'call-003',
      session_id: 'sess-100',
      task_id: 'task-summary-2',
      call_kind: 'auxiliary_summary',
      call_status: 'completed',
      usage_availability: 'exact',
      prompt_tokens: 300,
      completion_tokens: 100,
      total_tokens: 400,
      cost_usd: 0.008,
      provider_raw_status: 'success',
      timestamp_ms: 1791800003000,
    },
  ];

  it('renders summary statistics and flags financial audit risk when aborted calls exist', () => {
    render(<AbortedAuxiliaryUsageHUD stats={mockStatsWithUnknown} records={mockRecords} />);

    // Header title
    expect(screen.getByText(/Auxiliary Usage Ledger & Unknown-Usage Guard/i)).toBeInTheDocument();

    // Risk banner
    expect(screen.getByTestId('unknown-risk-banner')).toBeInTheDocument();
    expect(screen.getByText(/Financial Audit Protected/i)).toBeInTheDocument();

    // Top metrics
    expect(screen.getByTestId('total-calls-val')).toHaveTextContent('3');
    expect(screen.getByTestId('known-calls-val')).toHaveTextContent('2');
    expect(screen.getByTestId('unknown-calls-val')).toHaveTextContent('1');
    expect(screen.getByTestId('total-cost-val')).toHaveTextContent('$0.0240');
  });

  it('enforces anti-pseudo-free rules on aborted unknown calls', () => {
    render(<AbortedAuxiliaryUsageHUD stats={mockStatsWithUnknown} records={mockRecords} />);

    // Row presence
    expect(screen.getByTestId('ledger-row-task-audit-aborted')).toBeInTheDocument();

    // The aborted unknown call must explicitly say Usage-Unknown and Unaccounted
    const unknownTokenEl = screen.getByTestId('token-unknown-task-audit-aborted');
    expect(unknownTokenEl).toHaveTextContent('Usage-Unknown (Not 0)');

    const unknownCostEl = screen.getByTestId('cost-unknown-task-audit-aborted');
    expect(unknownCostEl).toHaveTextContent('Unaccounted');
  });

  it('handles refresh and reset button callbacks', () => {
    const handleRefresh = vi.fn();
    const handleReset = vi.fn();

    render(
      <AbortedAuxiliaryUsageHUD
        stats={mockStatsWithUnknown}
        records={mockRecords}
        onRefresh={handleRefresh}
        onReset={handleReset}
      />
    );

    const refreshBtn = screen.getByTestId('refresh-ledger-btn');
    fireEvent.click(refreshBtn);
    expect(handleRefresh).toHaveBeenCalledTimes(1);

    const resetBtn = screen.getByTestId('reset-ledger-btn');
    fireEvent.click(resetBtn);
    expect(handleReset).toHaveBeenCalledTimes(1);
  });

  it('filters rows by status and usage availability correctly', () => {
    render(<AbortedAuxiliaryUsageHUD stats={mockStatsWithUnknown} records={mockRecords} />);

    // Filter by ABORTED status
    const abortedBtn = screen.getByTestId('filter-status-aborted');
    fireEvent.click(abortedBtn);

    expect(screen.queryByTestId('ledger-row-task-primary-1')).not.toBeInTheDocument();
    expect(screen.getByTestId('ledger-row-task-audit-aborted')).toBeInTheDocument();

    // Filter by EXACT availability while ABORTED is selected -> empty state
    const exactBtn = screen.getByTestId('filter-avail-exact');
    fireEvent.click(exactBtn);

    expect(screen.queryByTestId('ledger-row-task-audit-aborted')).not.toBeInTheDocument();
    expect(screen.getByText(/No canonical ledger invocations found/i)).toBeInTheDocument();
  });

  it('renders clean audit banner when zero unknown-usage calls exist', () => {
    const cleanStats: AbortedUsageUnknownStatsItem = {
      ...mockStatsWithUnknown,
      unknown_usage_calls: 0,
      unknown_risk_flag: false,
    };

    render(<AbortedAuxiliaryUsageHUD stats={cleanStats} records={mockRecords} />);

    expect(screen.getByTestId('clean-audit-banner')).toBeInTheDocument();
    expect(
      screen.getByText(/All auxiliary model calls reconciled with exact token usage/i)
    ).toBeInTheDocument();
  });
});
