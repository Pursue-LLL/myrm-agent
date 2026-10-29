'use client';

/**
 * The reason line of an approval card is worded from the harness's stable reason code in the viewer's language;
 * a reason the harness did not code is shown as it was written.
 */
import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import SingleApprovalCard from '@/components/features/chat-window/SingleApprovalCard';
import type { ToolApprovalRequest } from '@/store/chat/types';

const worded = (key: string, values?: Record<string, string>) => (values?.subject ? `${key}|${values.subject}` : key);

vi.mock('next-intl', () => ({
  useLocale: () => 'en',
  useTranslations: () => worded,
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

function buildRequest(overrides: Partial<ToolApprovalRequest> = {}): ToolApprovalRequest {
  return {
    requestId: 'req-1',
    toolName: 'file_read_tool',
    toolInput: { paths: ['/Users/me/Downloads/bill.csv'] },
    reason: 'Path outside allowed zones: /Users/me/Downloads/bill.csv',
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
  render(<SingleApprovalCard request={request} onResolve={vi.fn(async () => {})} isLoading={false} />);
}

describe('SingleApprovalCard reason line', () => {
  it('words a coded reason from the catalog and does not show the English text', () => {
    renderCard(buildRequest({ reasonCode: 'path_outside_zones', reasonSubject: '/Users/me/Downloads/bill.csv' }));

    expect(screen.getByText(/reasons\.path_outside_zones\|\/Users\/me\/Downloads\/bill\.csv/)).toBeTruthy();
    expect(screen.queryByText(/Path outside allowed zones/)).toBeNull();
  });

  it('shows a reason the harness did not code as written', () => {
    renderCard(buildRequest({ reason: 'Socially irreversible operation (send) requires explicit human approval' }));

    expect(screen.getByText(/Socially irreversible operation/)).toBeTruthy();
  });

  it('shows no reason line when there is neither a code nor a reason', () => {
    renderCard(buildRequest({ reason: '' }));

    expect(screen.queryByText('reason:')).toBeNull();
  });
});
