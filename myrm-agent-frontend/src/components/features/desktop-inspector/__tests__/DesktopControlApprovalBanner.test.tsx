/** @vitest-environment jsdom */
'use client';

import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import DesktopControlApprovalBanner from '../DesktopControlApprovalBanner';
import useDesktopControlApprovalStore from '@/store/useDesktopControlApprovalStore';

const mockApiRequest = vi.fn();

const stableT = (key: string) => key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

vi.mock('@/lib/api', () => ({
  apiRequest: (...args: unknown[]) => mockApiRequest(...args),
}));

describe('DesktopControlApprovalBanner', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockApiRequest.mockResolvedValue({ ok: true });
    useDesktopControlApprovalStore.setState({
      pending: true,
      expired: false,
      denied: false,
      changed: false,
      requestId: 'req-desktop-1',
      reason: 'Control TextEdit',
      operation: 'desktop_interact(scroll, @d1)',
      appName: 'TextEdit',
      windowTitle: 'Untitled',
      requireAppApproval: true,
      messageId: 'msg-1',
      requestedAt: Date.now(),
    });
  });

  it('renders nothing when no pending approval', () => {
    useDesktopControlApprovalStore.setState({ pending: false });
    const { container } = render(<DesktopControlApprovalBanner />);
    expect(container.firstChild).toBeNull();
  });

  it('posts deny decision and shows denied confirmation', async () => {
    render(<DesktopControlApprovalBanner />);

    expect(screen.getByText('Control TextEdit')).toBeInTheDocument();

    await act(async () => {
      fireEvent.click(screen.getByTestId('desktop-control-deny'));
      await Promise.resolve();
    });

    await waitFor(() => {
      expect(mockApiRequest).toHaveBeenCalledWith('/webui/desktop/approval/resolve', {
        method: 'POST',
        body: JSON.stringify({
          request_id: 'req-desktop-1',
          granted: false,
          scope: 'once',
        }),
      });
    });
    // Deny keeps the card mounted on the confirmation view instead of vanishing.
    expect(useDesktopControlApprovalStore.getState().pending).toBe(true);
    expect(useDesktopControlApprovalStore.getState().denied).toBe(true);
    expect(screen.getByText('deniedNotice')).toBeInTheDocument();

    await act(async () => {
      fireEvent.click(screen.getByTestId('desktop-control-denied-dismiss'));
      await Promise.resolve();
    });
    expect(useDesktopControlApprovalStore.getState().pending).toBe(false);
  });

  it('posts allow-once decision and clears pending state', async () => {
    render(<DesktopControlApprovalBanner />);

    await act(async () => {
      fireEvent.click(screen.getByTestId('desktop-control-allow-once'));
      await Promise.resolve();
    });

    await waitFor(() => {
      expect(mockApiRequest).toHaveBeenCalledWith('/webui/desktop/approval/resolve', {
        method: 'POST',
        body: JSON.stringify({
          request_id: 'req-desktop-1',
          granted: true,
          scope: 'once',
        }),
      });
    });
    expect(useDesktopControlApprovalStore.getState().pending).toBe(false);
  });

  it('renders expired view and dismisses it', async () => {
    useDesktopControlApprovalStore.setState({ expired: true });
    render(<DesktopControlApprovalBanner />);

    expect(screen.getByText('expiredNotice')).toBeInTheDocument();

    await act(async () => {
      fireEvent.click(screen.getByTestId('desktop-control-expired-dismiss'));
      await Promise.resolve();
    });
    expect(useDesktopControlApprovalStore.getState().pending).toBe(false);
  });
});
