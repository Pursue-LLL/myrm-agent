'use client';

/**
 * A path approval offers the folders the harness planned; ticking the box sends exactly those with the approval,
 * and leaving it unticked sends nothing, so approving never widens access by itself.
 */
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import SingleApprovalCard from '@/components/features/chat-window/SingleApprovalCard';
import type { ToolApprovalRequest } from '@/store/chat/types';

const stableT = (key: string) => key;

vi.mock('next-intl', () => ({
  useLocale: () => 'en',
  useTranslations: () => stableT,
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

const FOLDERS = [
  { path: '/Users/me/Downloads', writable: false },
  { path: '/Users/me/reports', writable: true },
];

function buildRequest(overrides: Partial<ToolApprovalRequest> = {}): ToolApprovalRequest {
  return {
    requestId: 'req-read',
    toolName: 'file_read_tool',
    toolInput: { paths: ['/Users/me/Downloads/bill.csv'] },
    reason: '',
    timeoutSeconds: 60,
    expiresAt: Math.floor(Date.now() / 1000) + 60,
    timeoutBehavior: 'deny',
    messageId: 'msg-1',
    displayMode: 'approval',
    chatId: 'chat-1',
    actionMode: 'agent',
    ...overrides,
  };
}

function renderCard(request: ToolApprovalRequest) {
  const onResolve = vi.fn(async () => {});
  render(<SingleApprovalCard request={request} onResolve={onResolve} isLoading={false} />);
  return onResolve;
}

describe('SingleApprovalCard folder grant', () => {
  it('sends the offered folders with the approval once the box is ticked', () => {
    const onResolve = renderCard(buildRequest({ grantDirectories: FOLDERS }));

    fireEvent.click(screen.getByRole('checkbox', { name: 'grantDirectory' }));
    fireEvent.click(screen.getByRole('button', { name: 'approve' }));

    expect(onResolve).toHaveBeenCalledWith('req-read', 'approve', { grant_directories: FOLDERS });
  });

  it('sends no folder when the box is left unticked', () => {
    const onResolve = renderCard(buildRequest({ grantDirectories: FOLDERS }));

    fireEvent.click(screen.getByRole('button', { name: 'approve' }));

    expect(onResolve).toHaveBeenCalledWith('req-read', 'approve', {});
  });

  it('shows no folder toggle when the approval offers none', () => {
    renderCard(buildRequest());

    expect(screen.queryByRole('checkbox')).toBeNull();
  });
});
