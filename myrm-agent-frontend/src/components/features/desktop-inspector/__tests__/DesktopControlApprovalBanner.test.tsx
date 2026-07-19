/** @vitest-environment jsdom */
'use client';

import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import DesktopControlApprovalBanner from '../DesktopControlApprovalBanner';
import useDesktopControlApprovalStore from '@/store/useDesktopControlApprovalStore';

const mockApiRequest = vi.fn();

vi.mock('next-intl', () => ({
  useTranslations: () => (key: string) => key,
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

  it('posts deny decision and clears pending state', async () => {
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
});
