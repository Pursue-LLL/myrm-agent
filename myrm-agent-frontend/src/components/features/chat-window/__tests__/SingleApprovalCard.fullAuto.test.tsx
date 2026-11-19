'use client';

/**
 * In the full-auto tier the card approves a call for the viewer after a short delay, except a call the harness holds
 * for the viewer alone (a write to an instruction file, a git hook): that card waits for the viewer's own answer, and
 * its approve button stays usable.
 */
import { act, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import SingleApprovalCard from '@/components/features/chat-window/SingleApprovalCard';
import { usePermissionTierStore } from '@/components/features/chat-window/thinking-permission/usePermissionTierStore';
import type { ToolApprovalRequest } from '@/store/chat/types';

import { approvalRequest } from './approvalKit';

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

/** Renders the card and lets the delay of the client's own approval pass; returns what the card answered. */
function renderCardAndWait(overrides: Partial<ToolApprovalRequest> = {}) {
  const onResolve = vi.fn(async () => {});
  render(<SingleApprovalCard request={approvalRequest(overrides)} onResolve={onResolve} isLoading={false} />);
  act(() => {
    vi.advanceTimersByTime(1_000);
  });
  return onResolve;
}

describe('SingleApprovalCard in the full-auto tier', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    usePermissionTierStore.setState({ tier: 'full-auto' });
  });

  afterEach(() => {
    vi.useRealTimers();
    usePermissionTierStore.setState({ tier: 'strict' });
  });

  it('approves an ordinary call for the viewer', () => {
    const onResolve = renderCardAndWait();

    expect(onResolve).toHaveBeenCalledTimes(1);
    expect(onResolve).toHaveBeenCalledWith('req-1', 'approve', {});
    expect(screen.getByRole('button', { name: 'toolApproval.autoApproving' })).toBeDisabled();
  });

  it('leaves a call held for the viewer to the viewer', () => {
    const onResolve = renderCardAndWait({ heldForPerson: true });

    expect(onResolve).not.toHaveBeenCalled();
    const approve = screen.getByRole('button', { name: 'toolApproval.approve' });
    expect(approve).toBeEnabled();

    fireEvent.click(approve);

    expect(onResolve).toHaveBeenCalledTimes(1);
    expect(onResolve).toHaveBeenCalledWith('req-1', 'approve', {});
  });
});
