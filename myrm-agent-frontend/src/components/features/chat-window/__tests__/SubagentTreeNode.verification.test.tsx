/** @vitest-environment jsdom */
'use client';

import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const stableT = (key: string) => key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

vi.mock('@/store/chat/useSubagentStore', () => ({
  useSubagentStore: {
    getState: () => ({
      completeNode: vi.fn(),
      upsertNode: vi.fn(),
    }),
  },
  isNodeOvertime: () => false,
}));

vi.mock('@/lib/api', () => ({
  fetchWithTimeout: vi.fn(),
}));

vi.mock('sonner', () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
    warning: vi.fn(),
    info: vi.fn(),
    promise: vi.fn(),
    loading: vi.fn(),
    dismiss: vi.fn(),
    message: vi.fn(),
  },
}));

vi.mock('@/components/primitives/button', () => ({
  Button: ({ children, ...props }: React.ComponentProps<'button'> & { variant?: string; size?: string }) => (
    <button type="button" {...props}>
      {children}
    </button>
  ),
}));

vi.mock('@/components/features/app-shell/confirm-dialog', () => ({
  ConfirmDialog: () => null,
}));

vi.mock('../subagent/SubagentStream', () => ({
  StatusIcon: () => null,
  NodeStream: () => null,
  STATUS_ICON_MAP: {},
}));

import { SubagentTreeNode } from '../subagent/SubagentTree';
import type { TreeNode } from '@/lib/utils/subagentTree';

function nodeWithVerification(overrides: Partial<TreeNode> = {}): TreeNode {
  return {
    task_id: 'task-verified',
    parent_task_id: '',
    agent_type: 'worker',
    description: 'Research competitor pricing',
    status: 'completed',
    progress: 100,
    children: [],
    verification: {
      passed: true,
      rounds: 1,
      max_rounds: 2,
      confidence: 'HIGH',
      summary: 'All checks passed',
    },
    ...overrides,
  };
}

const renderNode = (node: TreeNode) => render(<SubagentTreeNode node={node} chatId="chat-1" setOpen={() => {}} />);

describe('SubagentTreeNode verification badge', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders a PASS badge when verification passed', () => {
    renderNode(nodeWithVerification());
    const badge = screen.getByTestId('subagent-verification-badge');
    expect(badge).toBeTruthy();
    expect(badge.getAttribute('data-verification-passed')).toBe('true');
    expect(badge.textContent).toContain('verificationPassed');
  });

  it('renders a FAIL badge when verification failed', () => {
    renderNode(
      nodeWithVerification({
        verification: {
          passed: false,
          rounds: 2,
          max_rounds: 2,
          confidence: 'LOW',
          summary: 'Edge case missing',
          findings: [{ severity: 'MAJOR', description: 'Missing null check' }],
        },
      }),
    );
    const badge = screen.getByTestId('subagent-verification-badge');
    expect(badge.getAttribute('data-verification-passed')).toBe('false');
    expect(badge.textContent).toContain('verificationFailed');
    expect(badge.textContent).toContain('2/2');
  });

  it('hides the badge when no verification present', () => {
    renderNode(nodeWithVerification({ verification: undefined }));
    expect(screen.queryByTestId('subagent-verification-badge')).toBeNull();
  });

  it('expands findings on click and collapses again', () => {
    renderNode(
      nodeWithVerification({
        verification: {
          passed: false,
          rounds: 2,
          max_rounds: 2,
          confidence: 'MEDIUM',
          summary: 'Broken',
          findings: [
            { severity: 'CRITICAL', description: 'Crash on empty input' },
            { severity: 'MINOR', description: 'Style nit' },
          ],
        },
      }),
    );
    const badge = screen.getByTestId('subagent-verification-badge');
    fireEvent.click(badge);
    expect(screen.getByText('verificationFindings')).toBeTruthy();
    expect(screen.getByText(/Crash on empty input/)).toBeTruthy();
    expect(screen.getByText(/Style nit/)).toBeTruthy();

    fireEvent.click(badge);
    expect(screen.queryByText('verificationFindings')).toBeNull();
  });

  it('does not expand when there are no findings', () => {
    renderNode(
      nodeWithVerification({
        verification: { passed: true, rounds: 1, max_rounds: 1, confidence: 'HIGH' },
      }),
    );
    const badge = screen.getByTestId('subagent-verification-badge');
    fireEvent.click(badge);
    expect(screen.queryByText('verificationFindings')).toBeNull();
  });

  it('shows rounds only when a multi-round budget is configured', () => {
    const { rerender } = renderNode(
      nodeWithVerification({
        verification: { passed: true, rounds: 1, max_rounds: 1, confidence: 'HIGH' },
      }),
    );
    const singleBadge = screen.getByTestId('subagent-verification-badge');
    expect(singleBadge.textContent).not.toContain('1/1');

    rerender(
      <SubagentTreeNode
        node={nodeWithVerification({
          verification: { passed: true, rounds: 3, max_rounds: 3, confidence: 'HIGH' },
        })}
        chatId="chat-1"
        setOpen={() => {}}
      />,
    );
    const multiBadge = screen.getByTestId('subagent-verification-badge');
    expect(multiBadge.textContent).toContain('3/3');
  });
});
