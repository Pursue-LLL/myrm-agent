import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import BudgetPolicySection from '../BudgetPolicySection';
import {
  getBudgetPolicy,
  getBudgetStatus,
  getFleetQuotaDeck,
  type BudgetPolicy,
  type BudgetStatus,
  type FleetQuotaItem,
} from '@/services/budget';

const stableT = (key: string) => key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

vi.mock('@/services/budget', () => ({
  getBudgetPolicy: vi.fn(),
  getBudgetStatus: vi.fn(),
  getFleetQuotaDeck: vi.fn(),
  updateBudgetPolicy: vi.fn(),
}));

describe('BudgetPolicySection', () => {
  const mockPolicy: BudgetPolicy = {
    enabled: true,
    daily_limit_usd: 15.0,
    session_limit_usd: 5.0,
    per_call_limit_usd: 0.5,
    warning_threshold: 0.8,
    finalization_reserve_pct: 0.15,
    action_on_exceeded: 'finalize',
  };

  const mockStatus: BudgetStatus = {
    status: 'warning',
    daily_spend_usd: 12.5,
    daily_limit_usd: 15.0,
    daily_percent: 83.3,
    active_sessions: 2,
    total_calls_today: 45,
    warning_triggered: true,
    finalization_triggered: false,
    exceeded_triggered: false,
  };

  const mockFleetItems: FleetQuotaItem[] = [
    {
      dimension: 'agent_profile',
      identifier: 'researcher_v2',
      spendUsd: 11.2,
      allocatedQuotaUsd: 12.0,
      utilizationPct: 93.33,
      tier: 'tier_2_soft_gate',
      activeSessions: 1,
      updatedAt: '2026-09-03T07:00:00Z',
    },
    {
      dimension: 'task_type',
      identifier: 'market_analysis',
      spendUsd: 4.5,
      allocatedQuotaUsd: 5.0,
      utilizationPct: 90.0,
      tier: 'tier_1_visibility',
      activeSessions: 2,
      updatedAt: '2026-09-03T07:05:00Z',
    },
  ];

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders four-tier progressive spend control ladder and fleet quota deck', async () => {
    vi.mocked(getBudgetPolicy).mockResolvedValue(mockPolicy);
    vi.mocked(getBudgetStatus).mockResolvedValue(mockStatus);
    vi.mocked(getFleetQuotaDeck).mockResolvedValue({ items: mockFleetItems });

    render(<BudgetPolicySection />);

    await waitFor(() => {
      expect(screen.getByText('fourTierSpendControlTitle')).toBeDefined();
    });

    expect(screen.getByText('tier1Label')).toBeDefined();
    expect(screen.getByText('tier2Label')).toBeDefined();
    expect(screen.getByText('tier3Label')).toBeDefined();
    expect(screen.getByText('tier4Label')).toBeDefined();

    expect(screen.getByText('fleetQuotaDeckTitle')).toBeDefined();
    expect(screen.getByText('researcher_v2')).toBeDefined();
    expect(screen.getByText('market_analysis')).toBeDefined();
  });
});
