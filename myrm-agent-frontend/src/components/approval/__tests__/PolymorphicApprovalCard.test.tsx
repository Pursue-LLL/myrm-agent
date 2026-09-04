'use client';

import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { PolymorphicApprovalCard } from '../PolymorphicApprovalCard';
import type { ApprovalPayload } from '@/store/useApprovalStore';

vi.mock('next-intl', () => ({
  useTranslations: (namespace: string) => (key: string) => `${namespace}.${key}`,
  useLocale: () => 'en',
}));

function renderCard(approval: ApprovalPayload) {
  return render(
    <PolymorphicApprovalCard approval={approval} onResolve={async () => Promise.resolve()} isSubmitting={false} />,
  );
}

describe('PolymorphicApprovalCard', () => {
  it('renders scope note for external subagent tool calls', () => {
    renderCard({
      approval_id: 'approval-scope-ext',
      user_id: 'user-1',
      action_type: 'subagent_approval',
      status: 'PENDING',
      severity: 'warning',
      payload: {
        tool_calls: [
          {
            name: 'send_message_tool',
            args: {
              target: 'slack:general',
              message: 'Weekly update',
            },
          },
        ],
      },
    });

    expect(screen.getByText('humanize.scope.external')).toBeInTheDocument();
  });

  it('renders scope note for local file write compact rows', () => {
    renderCard({
      approval_id: 'approval-scope-local',
      user_id: 'user-1',
      action_type: 'subagent_approval',
      status: 'PENDING',
      severity: 'warning',
      payload: {
        tool_calls: [
          {
            name: 'file_write_tool',
            args: {
              path: '/workspace/report.md',
              content: '# Report',
            },
          },
        ],
      },
    });

    expect(screen.getByText('humanize.scope.local')).toBeInTheDocument();
  });

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
    expect(screen.getByText('Dummy Native')).toBeInTheDocument();
    expect(screen.getByText('humanize.scope.local')).toBeInTheDocument();
    expect(screen.getByText(/"query": "hello_world"/)).toBeInTheDocument();
  });

  it('shows edit action for single shell subagent approval', () => {
    renderCard({
      approval_id: 'approval-edit',
      user_id: 'user-1',
      action_type: 'subagent_approval',
      status: 'PENDING',
      severity: 'warning',
      payload: {
        tool_calls: [{ name: 'bash_code_execute_tool', args: { command: 'ls' } }],
      },
    });

    expect(screen.getByRole('button', { name: /toolApproval\.edit/ })).toBeInTheDocument();
  });

  it('does not show edit for multi-tool subagent batch', () => {
    renderCard({
      approval_id: 'approval-no-edit',
      user_id: 'user-1',
      action_type: 'subagent_approval',
      status: 'PENDING',
      severity: 'warning',
      payload: {
        tool_calls: [
          { name: 'bash_code_execute_tool', args: { command: 'ls' } },
          { name: 'bash_code_execute_tool', args: { command: 'pwd' } },
        ],
      },
    });

    expect(screen.queryByRole('button', { name: /toolApproval\.edit/ })).not.toBeInTheDocument();
  });

  it('shows allow always action for subagent approvals', () => {
    renderCard({
      approval_id: 'approval-4',
      user_id: 'user-1',
      action_type: 'subagent_approval',
      status: 'PENDING',
      severity: 'warning',
      payload: {
        tool_calls: [{ name: 'bash_code_execute_tool', args: { command: 'ls' } }],
      },
    });

    expect(screen.getByRole('button', { name: 'toolApproval.allowAlways' })).toBeInTheDocument();
  });

  it('does not show allow always for non-subagent approvals', () => {
    renderCard({
      approval_id: 'approval-5',
      user_id: 'user-1',
      action_type: 'skill_draft',
      status: 'PENDING',
      severity: 'warning',
      payload: { content: '# draft' },
    });

    expect(screen.queryByRole('button', { name: 'toolApproval.allowAlways' })).not.toBeInTheDocument();
  });

  it('renders high-risk evaluate JS expression instead of action(ref)', () => {
    const expression = "document.querySelector('.pay').click()";
    renderCard({
      approval_id: 'approval-dom-eval',
      user_id: 'user-1',
      action_type: 'high_risk_dom_action',
      status: 'PENDING',
      severity: 'critical',
      reason: 'Mutating JS evaluate',
      payload: {
        action_type: 'high_risk_dom_action',
        tool_name: 'browser_manage_tool',
        tool_input: { action: 'evaluate', expression },
        page_url: 'https://shop.example.com/checkout',
      },
    });

    expect(screen.getByText('toolApproval.highRiskDomAction')).toBeInTheDocument();
    expect(screen.getByText('toolApproval.jsExpression')).toBeInTheDocument();
    expect(screen.getByText(expression)).toBeInTheDocument();
    expect(screen.queryByText(/evaluate\(undefined\)/)).not.toBeInTheDocument();
  });

  it('renders high-risk click target element and action ref', () => {
    renderCard({
      approval_id: 'approval-dom-click',
      user_id: 'user-1',
      action_type: 'high_risk_dom_action',
      status: 'PENDING',
      severity: 'critical',
      payload: {
        action_type: 'high_risk_dom_action',
        tool_name: 'browser_interact_tool',
        tool_input: { action: 'click', ref: 'e5', text: '' },
        element: { role: 'button', name: 'Delete Repository', ref: 'e5' },
        page_url: 'https://github.com/settings',
      },
    });

    expect(screen.getByText(/Delete Repository/)).toBeInTheDocument();
    expect(screen.getByText(/click\(e5\)/)).toBeInTheDocument();
  });

  it('renders action-only tool input when expression is absent', () => {
    renderCard({
      approval_id: 'approval-dom-action-only',
      user_id: 'user-1',
      action_type: 'high_risk_dom_action',
      status: 'PENDING',
      severity: 'critical',
      payload: {
        tool_input: { action: 'click', ref: 'e2', text: 'hello' },
      },
    });

    expect(screen.getByText(/click\(e2, "hello"\)/)).toBeInTheDocument();
    expect(screen.queryByText('toolApproval.jsExpression')).not.toBeInTheDocument();
  });

  it('renders page URL for high-risk DOM approval', () => {
    renderCard({
      approval_id: 'approval-dom-page-url',
      user_id: 'user-1',
      action_type: 'high_risk_dom_action',
      status: 'PENDING',
      severity: 'critical',
      payload: {
        tool_input: { action: 'evaluate', expression: 'document.title' },
        page_url: 'https://example.com/account',
      },
    });

    expect(screen.getByText('https://example.com/account')).toBeInTheDocument();
  });

  it('renders knowledge patch approval card with target type, content and rationale', () => {
    renderCard({
      approval_id: 'approval-knowledge-patch-1',
      user_id: 'user-1',
      action_type: 'knowledge_patch',
      status: 'PENDING',
      severity: 'info',
      reason: 'Session blind spot recommendation',
      payload: {
        title: 'Bastion SSH Setup',
        target_type: 'wiki',
        content: 'Bastion host is bastion.internal.org on port 2222',
        trigger_condition: 'Questions about bastion or SSH gateways',
        rationale: 'User asked repeatedly after query missed in conversation',
        confidence: 0.9,
        source_queries: ['How to connect to bastion?'],
      },
    });

    expect(screen.getByText('Bastion SSH Setup')).toBeInTheDocument();
    expect(screen.getByText('toolApproval.knowledgePatch.typeWiki')).toBeInTheDocument();
    expect(screen.getByText('Bastion host is bastion.internal.org on port 2222')).toBeInTheDocument();
    expect(screen.getByText('Questions about bastion or SSH gateways')).toBeInTheDocument();
    expect(screen.getByText('User asked repeatedly after query missed in conversation')).toBeInTheDocument();
    expect(screen.getByText('How to connect to bastion?')).toBeInTheDocument();
    expect(screen.getByText('90%')).toBeInTheDocument();
  });
});
