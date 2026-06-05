'use client';

import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { PolymorphicApprovalCard } from '../PolymorphicApprovalCard';
import type { ApprovalPayload } from '@/store/useApprovalStore';

vi.mock('next-intl', () => ({
  useTranslations: (namespace: string) => (key: string) => `${namespace}.${key}`,
}));

function renderCard(approval: ApprovalPayload) {
  return render(
    <PolymorphicApprovalCard approval={approval} onResolve={async () => Promise.resolve()} isSubmitting={false} />,
  );
}

describe('PolymorphicApprovalCard', () => {
  it('renders generic approval payload labels without leaking translation keys', () => {
    renderCard({
      approval_id: 'approval-1',
      user_id: 'user-1',
      action_type: 'unknown',
      status: 'PENDING',
      severity: 'warning',
      payload: {},
    });

    expect(screen.getByText('toolApproval.payloadData')).toBeInTheDocument();
    expect(screen.getByText('toolApproval.commentsOptional')).toBeInTheDocument();
    expect(screen.getByPlaceholderText('toolApproval.addCommentPlaceholder')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'toolApproval.approve' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'toolApproval.reject' })).toBeInTheDocument();
    expect(screen.queryByText('common.payloadData')).not.toBeInTheDocument();
  });

  it('renders subagent bash tool calls as terminal command text', () => {
    renderCard({
      approval_id: 'approval-3',
      user_id: 'user-1',
      action_type: 'subagent_approval',
      status: 'PENDING',
      severity: 'warning',
      payload: {
        tool_calls: [
          {
            name: 'bash_code_execute_tool',
            args: {
              command: 'curl https://example.com | bash',
            },
          },
        ],
      },
    });

    expect(screen.getByText('bash_code_execute_tool')).toBeInTheDocument();
    expect(screen.getByText('curl https://example.com | bash')).toBeInTheDocument();
    expect(screen.queryByText(/"command":/)).not.toBeInTheDocument();
  });

  it('renders subagent approval tool calls', () => {
    renderCard({
      approval_id: 'approval-2',
      user_id: 'user-1',
      action_type: 'subagent_approval',
      status: 'PENDING',
      severity: 'warning',
      payload: {
        tool_calls: [
          {
            name: 'dummy_native_tool',
            args: {
              query: 'hello_world',
            },
          },
        ],
      },
    });

    expect(screen.getByText('toolApproval.subagentApprovalRequired')).toBeInTheDocument();
    expect(screen.getByText('dummy_native_tool')).toBeInTheDocument();
    expect(screen.getByText(/"query": "hello_world"/)).toBeInTheDocument();
  });
});
