import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { SpendInterventionBanner } from '../SpendInterventionBanner';
import { confirmSoftSpendGate, type SpendInterventionDecision } from '@/services/budget';

const stableT = (key: string) => key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

vi.mock('@/services/budget', () => ({
  confirmSoftSpendGate: vi.fn(),
}));

describe('SpendInterventionBanner', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders Tier 2 soft gate banner with self-confirm button and handles click', async () => {
    vi.mocked(confirmSoftSpendGate).mockResolvedValue({
      confirmed: true,
      sessionId: 'sess_test_1',
    });

    const mockDecision: SpendInterventionDecision = {
      tier: 'tier_2_soft_gate',
      action: 'require_confirmation',
      currentSpendUsd: 9.2,
      quotaLimitUsd: 10.0,
      spendRatio: 0.92,
      message: 'Soft gate active. Please confirm to continue.',
      bypassToken: 'byp_token_123',
      isBlocked: true,
      decisionId: 'dec_1',
      createdAt: '2026-09-03T12:00:00Z',
    };

    const onConfirmMock = vi.fn();

    render(
      <SpendInterventionBanner decision={mockDecision} sessionId="sess_test_1" onBypassConfirmed={onConfirmMock} />,
    );

    expect(screen.getByText('softGateActive')).toBeInTheDocument();
    expect(screen.getByText('$9.20 / $10.00')).toBeInTheDocument();

    const confirmBtn = screen.getByRole('button', { name: /selfConfirmButton/i });
    expect(confirmBtn).toBeInTheDocument();

    fireEvent.click(confirmBtn);

    await waitFor(() => {
      expect(confirmSoftSpendGate).toHaveBeenCalledWith({
        sessionId: 'sess_test_1',
        bypassToken: 'byp_token_123',
      });
      expect(onConfirmMock).toHaveBeenCalled();
    });
  });

  it('renders Tier 3 seamless auto-downgrade notification without confirm button', () => {
    const mockDecision: SpendInterventionDecision = {
      tier: 'tier_3_auto_downgrade',
      action: 'switch_model',
      currentSpendUsd: 10.5,
      quotaLimitUsd: 10.0,
      spendRatio: 1.05,
      message: 'Auto-downgraded to economy model.',
      downgradeModelId: 'gpt-4o-mini',
      isBlocked: false,
      decisionId: 'dec_2',
      createdAt: '2026-09-03T12:00:00Z',
    };

    render(<SpendInterventionBanner decision={mockDecision} sessionId="sess_test_2" />);

    expect(screen.getByText('autoDowngradedActive')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /selfConfirmButton/i })).not.toBeInTheDocument();
  });
});
