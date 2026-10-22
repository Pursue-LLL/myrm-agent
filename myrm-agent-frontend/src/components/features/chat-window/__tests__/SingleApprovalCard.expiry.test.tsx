'use client';

/**
 * The server resolves an approval itself when its timeout ends, whichever view the card is in: an answer typed into
 * the edit or reject view after that point can no longer be applied, so those views must follow the same countdown
 * as the default view and refuse the confirmation once it is over.
 */
import { act, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import SingleApprovalCard from '@/components/features/chat-window/SingleApprovalCard';
import type { ToolApprovalRequest } from '@/store/chat/types';

vi.mock('next-intl', () => ({
  useLocale: () => 'en',
  useTranslations: (namespace: string) => (key: string) => `${namespace}.${key}`,
}));

vi.mock('sonner', () => ({
  toast: { error: vi.fn(), success: vi.fn() },
}));

vi.mock('@/store/useDesktopInspectorStore', () => ({
  default: (selector: (state: { viewData: null }) => unknown) => selector({ viewData: null }),
  selectScopedDesktopViewData: () => null,
}));

vi.mock('@/store/useBrowserInspectorStore', () => ({
  default: (selector: (state: { viewData: null }) => unknown) => selector({ viewData: null }),
  selectScopedBrowserViewData: () => null,
}));

const COUNTDOWN_SECONDS = 5;

function buildRequest(): ToolApprovalRequest {
  return {
    requestId: 'req-shell',
    toolName: 'bash_code_execute_tool',
    toolInput: { command: 'npm run test' },
    reason: '',
    timeoutSeconds: COUNTDOWN_SECONDS,
    expiresAt: Math.floor(Date.now() / 1000) + COUNTDOWN_SECONDS,
    timeoutBehavior: 'deny',
    messageId: 'msg-1',
    displayMode: 'approval',
    chatId: 'chat-1',
    actionMode: 'agent',
  };
}

function renderCard(): void {
  render(<SingleApprovalCard request={buildRequest()} onResolve={async () => {}} isLoading={false} />);
}

function runCountdownOut(): void {
  act(() => {
    vi.advanceTimersByTime((COUNTDOWN_SECONDS + 1) * 1000);
  });
}

describe('SingleApprovalCard countdown in every view', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('refuses the edit confirmation once the countdown ends while the edit view is open', () => {
    renderCard();
    fireEvent.click(screen.getByRole('button', { name: 'toolApproval.edit' }));
    expect(screen.getByRole('button', { name: 'toolApproval.confirmEdit' })).toBeEnabled();

    runCountdownOut();

    expect(screen.getByRole('button', { name: 'toolApproval.confirmEdit' })).toBeDisabled();
    expect(screen.getByText('toolApproval.expired')).toBeInTheDocument();
  });

  it('refuses the reject confirmation once the countdown ends while the reject view is open', () => {
    renderCard();
    fireEvent.click(screen.getByRole('button', { name: 'toolApproval.reject' }));
    expect(screen.getByRole('button', { name: 'toolApproval.confirmReject' })).toBeEnabled();

    runCountdownOut();

    expect(screen.getByRole('button', { name: 'toolApproval.confirmReject' })).toBeDisabled();
    expect(screen.getByText('toolApproval.expired')).toBeInTheDocument();
  });
});
