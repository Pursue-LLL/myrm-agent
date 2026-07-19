/** @vitest-environment jsdom */
'use client';

import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import DesktopPermissionsCard from '../DesktopPermissionsCard';

const mockApiRequest = vi.fn();

vi.mock('next-intl', () => ({
  useTranslations: () => (key: string, values?: Record<string, string>) => {
    if (key === 'platform' && values?.name) {
      return `platform:${values.name}`;
    }
    return key;
  },
}));

vi.mock('@/lib/deploy-mode', () => ({
  isLocalMode: vi.fn(() => true),
}));

vi.mock('@/lib/api', () => ({
  apiRequest: (...args: unknown[]) => mockApiRequest(...args),
}));

vi.mock('@/lib/utils/toast', () => ({
  toast: { success: vi.fn() },
}));

const ACCESSIBILITY_DEEPLINK =
  'x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility';

describe('DesktopPermissionsCard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('shows all-ready state when permissions are granted', async () => {
    mockApiRequest.mockResolvedValueOnce({
      accessibility: true,
      screen_recording: true,
      all_granted: true,
      platform: 'darwin',
      settings_deeplinks: {},
    });

    render(<DesktopPermissionsCard />);

    await waitFor(() => {
      expect(screen.getByText('allReady')).toBeInTheDocument();
    });
    expect(screen.getByText('platform:darwin')).toBeInTheDocument();
  });

  it('shows missing permissions and opens system deeplink', async () => {
    mockApiRequest.mockResolvedValueOnce({
      accessibility: false,
      screen_recording: true,
      all_granted: false,
      platform: 'darwin',
      settings_deeplinks: {
        accessibility: ACCESSIBILITY_DEEPLINK,
      },
    });

    const windowOpen = vi.spyOn(window, 'open').mockImplementation(() => null);

    render(<DesktopPermissionsCard />);

    await waitFor(() => {
      expect(screen.getByText('actionRequired')).toBeInTheDocument();
    });
    expect(screen.getAllByText('accessibility').length).toBeGreaterThan(0);
    expect(screen.getByText(ACCESSIBILITY_DEEPLINK)).toBeInTheDocument();

    const openButtons = screen.getAllByTitle('Open settings');
    await act(async () => {
      fireEvent.click(openButtons[0]);
    });

    expect(windowOpen).toHaveBeenCalledWith(ACCESSIBILITY_DEEPLINK, '_blank');
    windowOpen.mockRestore();
  });

  it('shows retry UI when permissions API fails', async () => {
    mockApiRequest.mockRejectedValueOnce(new Error('network'));

    render(<DesktopPermissionsCard />);

    await waitFor(() => {
      expect(screen.getByText('checkFailed')).toBeInTheDocument();
    });
  });
});
