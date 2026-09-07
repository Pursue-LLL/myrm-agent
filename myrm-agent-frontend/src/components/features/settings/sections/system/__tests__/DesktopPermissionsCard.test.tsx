/** @vitest-environment jsdom */
'use client';

import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const { mockApiRequest, mockOpenPermissionDeepLink } = vi.hoisted(() => ({
  mockApiRequest: vi.fn(),
  mockOpenPermissionDeepLink: vi.fn(),
}));

const stableT = (key: string, values?: Record<string, string>) => {
  if (key === 'platform' && values?.name) {
    return `platform:${values.name}`;
  }
  return key;
};

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

vi.mock('@/lib/deploy-mode', () => ({
  isLocalMode: vi.fn(() => true),
}));

vi.mock('@/lib/api', () => ({
  apiRequest: (...args: unknown[]) => mockApiRequest(...args),
}));

vi.mock('@/lib/utils/toast', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

vi.mock('@/lib/desktop/permissionDeepLink', () => ({
  isSystemSettingsDeepLink: (url: string) => url.startsWith('x-apple.systempreferences:'),
  openPermissionDeepLink: (...args: unknown[]) => mockOpenPermissionDeepLink(...args),
}));

import DesktopPermissionsCard from '../DesktopPermissionsCard';

const ACCESSIBILITY_DEEPLINK = 'x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility';

const GRANT_ONLY_PERMISSIONS = {
  accessibility: true,
  screen_recording: true,
  screen_recording_capturable: null,
  all_granted: true,
  capture_ready: false,
  platform: 'darwin',
  settings_deeplinks: {},
};

const CAPTURE_READY_PERMISSIONS = {
  ...GRANT_ONLY_PERMISSIONS,
  screen_recording_capturable: true,
  capture_ready: true,
};

function mockDesktopApis(options?: { permissions?: unknown; trust?: unknown; trustReject?: boolean }) {
  mockApiRequest.mockImplementation((url: string, init?: { method?: string }) => {
    if (typeof url === 'string' && url.startsWith('/webui/desktop/permissions')) {
      if (options?.permissions instanceof Error) {
        return Promise.reject(options.permissions);
      }
      return Promise.resolve(options?.permissions ?? GRANT_ONLY_PERMISSIONS);
    }
    if (url === '/webui/desktop/trust/apps') {
      if (init?.method === 'DELETE') {
        return Promise.resolve({ ok: true });
      }
      if (options?.trustReject) {
        return Promise.reject(new Error('network'));
      }
      return Promise.resolve(options?.trust ?? { apps: [] });
    }
    return Promise.reject(new Error(`unexpected api: ${url}`));
  });
}

describe('DesktopPermissionsCard', () => {
  beforeEach(() => {
    mockApiRequest.mockReset();
    mockOpenPermissionDeepLink.mockReset();
  });

  afterEach(() => {
    cleanup();
  });

  it('shows unverified state on first load without capture probe', async () => {
    mockDesktopApis();

    render(<DesktopPermissionsCard />);

    await waitFor(() => {
      expect(screen.getByText('grantsOkCaptureUnverified')).toBeInTheDocument();
    });
    expect(screen.getByText('captureUnverifiedHint')).toBeInTheDocument();
    expect(screen.getByText('statusUnverified')).toBeInTheDocument();
    expect(mockApiRequest).toHaveBeenCalledWith('/webui/desktop/permissions', { silent: true });
  });

  it('recheck with capture probe can reach all-ready', async () => {
    mockApiRequest.mockImplementation((url: string, init?: { method?: string }) => {
      if (url === '/webui/desktop/permissions') {
        return Promise.resolve(GRANT_ONLY_PERMISSIONS);
      }
      if (url === '/webui/desktop/permissions?probe_capture=true') {
        return Promise.resolve(CAPTURE_READY_PERMISSIONS);
      }
      if (url === '/webui/desktop/trust/apps') {
        if (init?.method === 'DELETE') {
          return Promise.resolve({ ok: true });
        }
        return Promise.resolve({ apps: [] });
      }
      return Promise.reject(new Error(`unexpected api: ${url}`));
    });

    render(<DesktopPermissionsCard />);

    await waitFor(() => {
      expect(screen.getByText('grantsOkCaptureUnverified')).toBeInTheDocument();
    });

    await act(async () => {
      fireEvent.click(screen.getByTitle('recheckWithCapture'));
    });

    await waitFor(() => {
      expect(screen.getByText('allReady')).toBeInTheDocument();
    });
    expect(mockApiRequest).toHaveBeenCalledWith('/webui/desktop/permissions?probe_capture=true', {
      silent: true,
    });
  });

  it('shows captureFailed header when grants ok but probe fails', async () => {
    mockDesktopApis({
      permissions: {
        accessibility: true,
        screen_recording: true,
        screen_recording_capturable: false,
        all_granted: true,
        capture_ready: false,
        platform: 'darwin',
        settings_deeplinks: {},
      },
    });

    render(<DesktopPermissionsCard />);

    await waitFor(() => {
      expect(screen.getByText('captureFailed')).toBeInTheDocument();
    });
    expect(screen.getByText('captureFailedHint')).toBeInTheDocument();
    expect(screen.queryByText('actionRequired')).not.toBeInTheDocument();
    expect(screen.queryByText('grantsOkCaptureUnverified')).not.toBeInTheDocument();
  });

  it('shows missing permissions and opens system deeplink', async () => {
    mockDesktopApis({
      permissions: {
        accessibility: false,
        screen_recording: true,
        screen_recording_capturable: null,
        all_granted: false,
        capture_ready: false,
        platform: 'darwin',
        settings_deeplinks: {
          accessibility: ACCESSIBILITY_DEEPLINK,
        },
      },
    });

    render(<DesktopPermissionsCard />);

    await waitFor(() => {
      expect(screen.getByText('actionRequired')).toBeInTheDocument();
    });
    expect(screen.getAllByText('accessibility').length).toBeGreaterThan(0);
    expect(screen.getByText(ACCESSIBILITY_DEEPLINK)).toBeInTheDocument();

    const openButtons = screen.getAllByTitle('openSettings');
    await act(async () => {
      fireEvent.click(openButtons[0]);
    });

    expect(mockOpenPermissionDeepLink).toHaveBeenCalledWith(ACCESSIBILITY_DEEPLINK);
  });

  it('shows retry UI when permissions API fails', async () => {
    mockDesktopApis({ permissions: new Error('network') });

    render(<DesktopPermissionsCard />);

    await waitFor(() => {
      expect(screen.getByText('checkFailed')).toBeInTheDocument();
    });
  });

  it('lists trusted apps and revokes one', async () => {
    mockDesktopApis({
      trust: {
        apps: [{ trust_key: 'safari', display_name: 'Safari', app_id: '', scope: 'always' }],
      },
    });

    render(<DesktopPermissionsCard />);

    await waitFor(() => {
      expect(screen.getByText('Safari')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole('button', { name: 'trustedAppsRevoke' }));

    await waitFor(() => {
      expect(mockApiRequest).toHaveBeenCalledWith('/webui/desktop/trust/apps', {
        method: 'DELETE',
        body: JSON.stringify({ trust_key: 'safari' }),
      });
    });
  });

  it('shows trusted-apps retry UI when trust API fails', async () => {
    mockDesktopApis({ trustReject: true });

    render(<DesktopPermissionsCard />);

    await waitFor(() => {
      expect(screen.getByText('trustedAppsLoadFailed')).toBeInTheDocument();
    });
    expect(screen.queryByText('trustedAppsEmpty')).not.toBeInTheDocument();
  });
});
