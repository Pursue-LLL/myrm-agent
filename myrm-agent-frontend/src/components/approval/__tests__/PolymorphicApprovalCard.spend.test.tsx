import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { PolymorphicApprovalCard } from '../PolymorphicApprovalCard';
import type { ApprovalPayload } from '@/store/useApprovalStore';

// Stable mock references to prevent infinite re-rendering and pass CI stability gate
const stableT = (key: string) => {
  if (key === 'spendProtection.title') return 'Financial Transaction Protection';
  if (key === 'spendProtection.amount') return 'Charge Amount';
  if (key === 'spendProtection.tamperProtected') return 'SHA-256 Tamper Protected';
  if (key === 'approve') return 'Approve';
  if (key === 'reject') return 'Reject';
  return key;
};

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

vi.mock('next-themes', () => ({
  useTheme: () => ({ resolvedTheme: 'light' }),
}));

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn() }),
}));

describe('PolymorphicApprovalCard Financial Spend Protection', () => {
  it('renders financial spend banner with amount, currency and tamper protection badge', () => {
    const mockOnResolve = vi.fn().mockResolvedValue(undefined);
    const approval: ApprovalPayload = {
      approval_id: 'app_spend_1',
      user_id: 'usr_1',
      action_type: 'subagent_approval',
      status: 'pending',
      severity: 'high',
      payload: {
        tool_calls: [
          { name: 'mcp__stripe__charge_customer', args: { amount: 35.5, currency: 'USD' } },
        ],
        reviewConfigs: [
          {
            isSpend: true,
            spendAmount: 35.5,
            spendCurrency: 'USD',
            actionDigest: 'sha256_mock_digest_123',
            hideAllowAlways: true,
          },
        ],
      },
    };

    render(
      <PolymorphicApprovalCard
        approval={approval}
        onResolve={mockOnResolve}
        isSubmitting={false}
      />
    );

    // Verify title, amount, and badge
    expect(screen.getByText('Financial Transaction Protection')).toBeDefined();
    expect(screen.getByText('35.50 USD')).toBeDefined();
    expect(screen.getByText('SHA-256 Tamper Protected')).toBeDefined();

    // Verify allowAlways button is hidden
    expect(screen.queryByText('allowAlways')).toBeNull();
  });

  it('passes action_digest in extra payload when user approves financial spend', () => {
    const mockOnResolve = vi.fn().mockResolvedValue(undefined);
    const approval: ApprovalPayload = {
      approval_id: 'app_spend_2',
      user_id: 'usr_1',
      action_type: 'subagent_approval',
      status: 'pending',
      severity: 'high',
      payload: {
        tool_calls: [
          { name: 'cloud_purchase_tool', args: { amount: 80.0, currency: 'USD' } },
        ],
        reviewConfigs: [
          {
            isSpend: true,
            spendAmount: 80.0,
            spendCurrency: 'USD',
            actionDigest: 'sha256_exact_digest_456',
            hideAllowAlways: true,
          },
        ],
      },
    };

    render(
      <PolymorphicApprovalCard
        approval={approval}
        onResolve={mockOnResolve}
        isSubmitting={false}
      />
    );

    const approveBtn = screen.getByText('Approve');
    fireEvent.click(approveBtn);

    expect(mockOnResolve).toHaveBeenCalledTimes(1);
    expect(mockOnResolve).toHaveBeenCalledWith(
      'approve',
      '',
      undefined,
      expect.objectContaining({
        action_digest: 'sha256_exact_digest_456',
        actionDigest: 'sha256_exact_digest_456',
      })
    );
  });

  it('passes action_digest when user overrides smart-denied financial spend', () => {
    const mockOnResolve = vi.fn().mockResolvedValue(undefined);
    const approval: ApprovalPayload = {
      approval_id: 'app_spend_smart_denied',
      user_id: 'usr_1',
      action_type: 'subagent_approval',
      status: 'pending',
      severity: 'high',
      payload: {
        tool_calls: [
          { name: 'cloud_purchase_tool', args: { amount: 150.0, currency: 'USD' } },
        ],
        reviewConfigs: [
          {
            isSpend: true,
            spendAmount: 150.0,
            spendCurrency: 'USD',
            actionDigest: 'sha256_smart_denied_digest_789',
            smartDenied: true,
            hideAllowAlways: true,
          },
        ],
      },
    };

    render(
      <PolymorphicApprovalCard
        approval={approval}
        onResolve={mockOnResolve}
        isSubmitting={false}
      />
    );

    const overrideBtn = screen.getByText('smartDenied.overrideOnce');
    fireEvent.click(overrideBtn);

    expect(mockOnResolve).toHaveBeenCalledTimes(1);
    expect(mockOnResolve).toHaveBeenCalledWith(
      'approve',
      '',
      undefined,
      expect.objectContaining({
        action_digest: 'sha256_smart_denied_digest_789',
        actionDigest: 'sha256_smart_denied_digest_789',
      })
    );
  });
});
