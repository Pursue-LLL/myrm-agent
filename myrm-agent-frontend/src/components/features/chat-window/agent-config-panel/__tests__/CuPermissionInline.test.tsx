/** @vitest-environment jsdom */
'use client';

import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { CuPermissionInline } from '../CuPermissionInline';

const mockApiRequest = vi.fn();

vi.mock('@/lib/api', () => ({
  apiRequest: (...args: unknown[]) => mockApiRequest(...args),
}));

vi.mock('@tauri-apps/plugin-shell', () => ({
  open: vi.fn(() => Promise.reject(new Error('not tauri'))),
}));

const tPanel = (key: string) => key;

const ACCESSIBILITY_DEEPLINK = 'x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility';

describe('CuPermissionInline', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('shows unverified capture state on first load without probe', async () => {
    mockApiRequest.mockResolvedValueOnce({
      accessibility: true,
      screen_recording: true,
      screen_recording_capturable: null,
      all_granted: true,
      capture_ready: false,
      platform: 'darwin',
      settings_deeplinks: {},
    });

    render(<CuPermissionInline tPanel={tPanel} />);

    await waitFor(() => {
      expect(screen.getByText('cuPermission.grantsOkCaptureUnverified')).toBeInTheDocument();
    });
    expect(mockApiRequest).toHaveBeenCalledWith('/webui/desktop/permissions', { silent: true });
  });

  it('shows verified state when capture probe passed', async () => {
    mockApiRequest.mockResolvedValueOnce({
      accessibility: true,
      screen_recording: true,
      screen_recording_capturable: true,
      all_granted: true,
      capture_ready: true,
      platform: 'darwin',
      settings_deeplinks: {},
    });

    render(<CuPermissionInline tPanel={tPanel} />);

    await waitFor(() => {
      expect(screen.getByText('cuPermission.allGranted')).toBeInTheDocument();
    });
  });

  it('recheck probes capture and can reach verified', async () => {
    mockApiRequest
      .mockResolvedValueOnce({
        accessibility: true,
        screen_recording: true,
        screen_recording_capturable: null,
        all_granted: true,
        capture_ready: false,
        platform: 'darwin',
        settings_deeplinks: {},
      })
      .mockResolvedValueOnce({
        accessibility: true,
        screen_recording: true,
        screen_recording_capturable: true,
        all_granted: true,
        capture_ready: true,
        platform: 'darwin',
        settings_deeplinks: {},
      });

    render(<CuPermissionInline tPanel={tPanel} />);

    await waitFor(() => {
      expect(screen.getByText('cuPermission.grantsOkCaptureUnverified')).toBeInTheDocument();
    });

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /cuPermission.recheckBtn/ }));
    });

    await waitFor(() => {
      expect(screen.getByText('cuPermission.allGranted')).toBeInTheDocument();
    });
    expect(mockApiRequest).toHaveBeenLastCalledWith(
      '/webui/desktop/permissions?probe_capture=true',
      { silent: true },
    );
  });

  it('shows missing permissions and opens settings deeplink', async () => {
    mockApiRequest.mockResolvedValueOnce({
      accessibility: false,
      screen_recording: true,
      screen_recording_capturable: null,
      all_granted: false,
      capture_ready: false,
      platform: 'darwin',
      settings_deeplinks: {
        accessibility: ACCESSIBILITY_DEEPLINK,
      },
    });

    const windowOpen = vi.spyOn(window, 'open').mockImplementation(() => null);

    render(<CuPermissionInline tPanel={tPanel} />);

    await waitFor(() => {
      expect(screen.getByText('cuPermission.missing')).toBeInTheDocument();
    });
    expect(screen.getByText('cuPermission.accessibilityMissing')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /cuPermission.openSettings/ })).toBeInTheDocument();

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /cuPermission.openSettings/ }));
    });

    await waitFor(() => {
      expect(windowOpen).toHaveBeenCalledWith(
        'https://support.apple.com/guide/mac-help/allow-accessibility-apps-to-access-your-mac-mh43185/mac',
        '_blank',
      );
    });

    windowOpen.mockRestore();
  });

  it('shows capture not ready when probe fails', async () => {
    mockApiRequest.mockResolvedValueOnce({
      accessibility: true,
      screen_recording: true,
      screen_recording_capturable: false,
      all_granted: true,
      capture_ready: false,
      platform: 'darwin',
      settings_deeplinks: {},
    });

    render(<CuPermissionInline tPanel={tPanel} />);

    await waitFor(() => {
      expect(screen.getByText('cuPermission.missing')).toBeInTheDocument();
    });
    expect(screen.getByText('cuPermission.captureNotReady')).toBeInTheDocument();
  });

  it('renders error state when the permissions API fails', async () => {
    mockApiRequest.mockRejectedValueOnce(new Error('network'));

    render(<CuPermissionInline tPanel={tPanel} />);

    await waitFor(() => {
      expect(screen.getByText('cuPermission.checkFailed')).toBeInTheDocument();
    });
    expect(screen.getByRole('button', { name: /cuPermission.recheckBtn/ })).toBeInTheDocument();
  });
});
