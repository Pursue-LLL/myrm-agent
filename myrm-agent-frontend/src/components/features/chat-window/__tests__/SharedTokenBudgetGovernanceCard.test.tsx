import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import {
  SharedTokenBudgetGovernanceCard,
  SharedTokenBudgetSnapshotData,
} from '../SharedTokenBudgetGovernanceCard';

describe('SharedTokenBudgetGovernanceCard', () => {
  it('renders initial fallback state and handles dismiss', () => {
    const handleDismiss = vi.fn();
    render(
      <SharedTokenBudgetGovernanceCard
        chatId="session-fallback-01"
        onDismiss={handleDismiss}
      />
    );

    expect(screen.getByTestId('token-budget-governance-card')).toBeInTheDocument();
    expect(screen.getByTestId('stat-total-tokens')).toHaveTextContent('0');
    expect(screen.getByTestId('stat-routing-ratio')).toHaveTextContent('0.0%');
    expect(screen.getByTestId('stat-doctor-nudges')).toHaveTextContent('0');
    expect(screen.getByTestId('empty-alerts')).toBeInTheDocument();

    const dismissBtn = screen.getByRole('button', { name: /Dismiss dialog/i });
    fireEvent.click(dismissBtn);
    expect(handleDismiss).toHaveBeenCalledTimes(1);
  });

  it('renders provided initial snapshot and displays existing doctor nudges', () => {
    const customSnapshot: SharedTokenBudgetSnapshotData = {
      session_id: 'session-custom-02',
      primary_model: 'claude-3-5-sonnet',
      shared_token_ceiling: 150000,
      total_tokens_spent: 45000,
      routing_tokens_spent: 18000,
      execution_tokens_spent: 27000,
      routing_ratio: 0.4,
      role_budgets: {
        orchestrator: {
          role_name: 'orchestrator',
          token_ceiling: 25000,
          stop_condition: 'halt_and_report',
          allow_overflow: false,
        },
      },
      role_usage: {
        orchestrator: 18000,
      },
      active_alerts: [
        {
          alert_id: 'alert-warn-001',
          severity: 'warning',
          message: 'Routing overhead exceeds threshold.',
          handoff_count: 2,
          routing_ratio: 0.4,
          suggested_action: 'Consolidate routing prompts.',
          created_at: 1000,
        },
      ],
    };

    render(
      <SharedTokenBudgetGovernanceCard
        chatId="session-custom-02"
        initialSnapshot={customSnapshot}
      />
    );

    expect(screen.getByTestId('stat-total-tokens')).toHaveTextContent('45,000');
    expect(screen.getByTestId('stat-routing-ratio')).toHaveTextContent('40.0%');
    expect(screen.getByTestId('stat-doctor-nudges')).toHaveTextContent('1');
    expect(screen.getByTestId('alert-item-alert-warn-001')).toBeInTheDocument();
    expect(screen.getByText(/Consolidate routing prompts/i)).toBeInTheDocument();
  });

  it('records routing and execution token consumption accurately', () => {
    render(<SharedTokenBudgetGovernanceCard chatId="session-consume-03" />);

    expect(screen.getByTestId('stat-total-tokens')).toHaveTextContent('0');

    // Record routing overhead: 1,200 tokens
    fireEvent.click(screen.getByTestId('btn-record-routing'));
    expect(screen.getByTestId('stat-total-tokens')).toHaveTextContent('1,200');
    expect(screen.getByTestId('stat-routing-ratio')).toHaveTextContent('100.0%');
    expect(screen.getByTestId('status-message')).toHaveTextContent(
      "Recorded 1200 tokens for 'routing_overhead'"
    );

    // Record execution payload: 2,500 tokens (Total = 3,700, Routing = 1,200 / 3,700 ≈ 32.4%)
    fireEvent.click(screen.getByTestId('btn-record-execution'));
    expect(screen.getByTestId('stat-total-tokens')).toHaveTextContent('3,700');
    expect(screen.getByTestId('stat-routing-ratio')).toHaveTextContent('32.4%');
    expect(screen.getByTestId('status-message')).toHaveTextContent(
      "Recorded 2500 tokens for 'execution_payload'"
    );
  });

  it('triggers critical Doctor Nudge upon 5x repetitive handoff loop', () => {
    render(<SharedTokenBudgetGovernanceCard chatId="session-handoff-04" />);

    expect(screen.getByTestId('stat-doctor-nudges')).toHaveTextContent('0');

    // Simulate repetitive handoffs
    fireEvent.click(screen.getByTestId('btn-simulate-handoffs'));

    expect(screen.getByTestId('stat-doctor-nudges')).toHaveTextContent('1');
    expect(screen.getByTestId('status-message')).toHaveTextContent(
      'Doctor Nudge triggered: 5x repetitive handoff loop intercepted!'
    );
    expect(
      screen.getByText(/Subagents are bouncing tasks without execution payload/i)
    ).toBeInTheDocument();
  });

  it('simulates fail-closed precheck blocking and governor reset', () => {
    render(<SharedTokenBudgetGovernanceCard chatId="session-reset-05" />);

    // Test precheck simulation
    fireEvent.click(screen.getByTestId('btn-simulate-precheck'));
    expect(screen.getByTestId('status-message')).toHaveTextContent(
      'Precheck Blocked (Fail-Closed): Requested 25,000 tokens exceeds remaining per-role ceiling'
    );

    // Consume some tokens first
    fireEvent.click(screen.getByTestId('btn-record-routing'));
    expect(screen.getByTestId('stat-total-tokens')).toHaveTextContent('1,200');

    // Test reset
    fireEvent.click(screen.getByTestId('btn-reset'));
    expect(screen.getByTestId('stat-total-tokens')).toHaveTextContent('0');
    expect(screen.getByTestId('stat-routing-ratio')).toHaveTextContent('0.0%');
    expect(screen.getByTestId('status-message')).toHaveTextContent('Token budget governor reset.');
  });
});
