'use client';

import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import VisualApprovalUnavailableCard from '@/components/features/chat-window/approval/VisualApprovalUnavailableCard';
import type { ToolApprovalRequest } from '@/store/chat/types';

vi.mock('next-intl', () => ({
  useTranslations: () => (key: string) => key,
}));

vi.mock('@/components/features/chat-window/SingleApprovalCard', () => ({
  default: () => <div data-testid="single-approval-card-stub" />,
}));

const request: ToolApprovalRequest = {
  requestId: 'req-unavailable',
  toolName: 'desktop_interact',
  toolInput: { ref: 'e1' },
  reason: 'Click delete',
  timeoutSeconds: 60,
  expiresAt: Math.floor(Date.now() / 1000) + 60,
  timeoutBehavior: 'deny',
  messageId: 'msg-1',
  displayMode: 'approval',
  chatId: 'chat-1',
  actionMode: 'agent',
};

describe('VisualApprovalUnavailableCard', () => {
  it('renders permission fallback with retry and text approval stub', () => {
    const onRetrySnapshot = vi.fn();

    render(
      <VisualApprovalUnavailableCard
        request={request}
        reason="permission"
        onRetrySnapshot={onRetrySnapshot}
        onResolve={async () => {}}
        isLoading={false}
        isRetrying={false}
      />,
    );

    expect(screen.getByTestId('visual-approval-unavailable-card')).toBeInTheDocument();
    expect(screen.getByText('visualApprovalUnavailablePermission')).toBeInTheDocument();
    expect(screen.getByText('visualApprovalRetrySnapshot')).toBeInTheDocument();
    expect(screen.getByTestId('single-approval-card-stub')).toBeInTheDocument();

    fireEvent.click(screen.getByText('visualApprovalRetrySnapshot'));
    expect(onRetrySnapshot).toHaveBeenCalledTimes(1);
  });

  it('renders fetch failure copy when snapshot cannot be loaded', () => {
    render(
      <VisualApprovalUnavailableCard
        request={request}
        reason="fetch_failed"
        onRetrySnapshot={() => {}}
        onResolve={async () => {}}
        isLoading={false}
        isRetrying={false}
      />,
    );

    expect(screen.getByText('visualApprovalUnavailableFetchFailed')).toBeInTheDocument();
  });
});
