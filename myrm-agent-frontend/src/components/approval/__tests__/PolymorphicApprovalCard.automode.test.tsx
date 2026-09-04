import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { PolymorphicApprovalCard } from '../PolymorphicApprovalCard';
import type { ApprovalPayload } from '@/store/useApprovalStore';

// Stable mock translations
const stableT = (key: string) => {
  if (key === 'autoModeSuspended.title') return 'Auto Mode Suspended';
  if (key === 'autoModeSuspended.consecutiveReason') return 'Suspended after 3 consecutive safety denials.';
  if (key === 'autoModeSuspended.totalReason') return 'Suspended after reaching 20 total security denials.';
  if (key === 'sociallyIrreversible.title') return 'Socially Irreversible Action';
  if (key === 'sociallyIrreversible.description') return 'This operation affects external systems and cannot be undone locally.';
  if (key === 'approve') return 'Approve';
  if (key === 'reject') return 'Reject';
  return key;
};

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
  useLocale: () => 'en',
}));

vi.mock('next-themes', () => ({
  useTheme: () => ({ resolvedTheme: 'light' }),
}));

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn() }),
}));

describe('PolymorphicApprovalCard Auto Mode Production Hardening', () => {
  it('renders consecutive auto mode suspended warning banner', () => {
    const mockOnResolve = vi.fn().mockResolvedValue(undefined);
    const approval: ApprovalPayload = {
      approval_id: 'app_automode_1',
      user_id: 'usr_1',
      action_type: 'subagent_approval',
      status: 'pending',
      severity: 'high',
      payload: {
        tool_calls: [
          { name: 'bash_code_execute_tool', args: { command: 'python script.py' } },
        ],
        reviewConfigs: [
          {
            autoModeSuspended: 'consecutive',
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

    expect(screen.getByText('Auto Mode Suspended')).toBeDefined();
    expect(screen.getByText('Suspended after 3 consecutive safety denials.')).toBeDefined();
  });

  it('renders total auto mode suspended warning banner', () => {
    const mockOnResolve = vi.fn().mockResolvedValue(undefined);
    const approval: ApprovalPayload = {
      approval_id: 'app_automode_2',
      user_id: 'usr_1',
      action_type: 'subagent_approval',
      status: 'pending',
      severity: 'high',
      payload: {
        tool_calls: [
          { name: 'bash_code_execute_tool', args: { command: 'python script.py' } },
        ],
        reviewConfigs: [
          {
            autoModeSuspended: 'total',
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

    expect(screen.getByText('Auto Mode Suspended')).toBeDefined();
    expect(screen.getByText('Suspended after reaching 20 total security denials.')).toBeDefined();
  });

  it('renders socially irreversible operation warning banner', () => {
    const mockOnResolve = vi.fn().mockResolvedValue(undefined);
    const approval: ApprovalPayload = {
      approval_id: 'app_automode_3',
      user_id: 'usr_1',
      action_type: 'subagent_approval',
      status: 'pending',
      severity: 'high',
      payload: {
        tool_calls: [
          { name: 'bash_code_execute_tool', args: { command: 'git push origin main' } },
        ],
        reviewConfigs: [
          {
            sociallyIrreversible: true,
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

    expect(screen.getByText('Socially Irreversible Action')).toBeDefined();
    expect(screen.getByText('This operation affects external systems and cannot be undone locally.')).toBeDefined();
  });
});
