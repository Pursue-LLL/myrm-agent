/** @vitest-environment jsdom */
'use client';

import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { DoctorDashboard } from '../DoctorDashboard';
import type { DoctorResponse } from '@/services/runtime-health';

const mockGetRuntimeDoctor = vi.fn<() => Promise<DoctorResponse>>();

vi.mock('next-intl', () => ({
  useTranslations: () => (key: string) => key,
}));

vi.mock('sonner', () => ({
  toast: { error: vi.fn() },
}));

vi.mock('@/services/runtime-health', () => ({
  getRuntimeDoctor: () => mockGetRuntimeDoctor(),
}));

vi.mock('@/lib/utils/diagnostic-export', () => ({
  copyDiagnosticMarkdown: vi.fn(async () => true),
  downloadDiagnosticJson: vi.fn(),
}));

vi.mock('../GuidedRepairCard', () => ({
  GuidedRepairCard: () => null,
}));

vi.mock('@tauri-apps/plugin-shell', () => ({
  open: vi.fn(() => Promise.reject(new Error('not tauri'))),
}));

const ACCESSIBILITY_DEEPLINK =
  'x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility';

const warnDesktopControlDoctor: DoctorResponse = {
  harness: [
    {
      component_name: 'DesktopControl',
      status: 'warn',
      code: 'WARN_DESKTOP_PERMISSIONS_MISSING',
      message: 'Missing desktop permissions: Accessibility.',
      detail: 'Platform: darwin.',
      fix_suggestion: 'Grant the missing permissions in system settings, then recheck.',
      meta_data: {
        accessibility: false,
        screen_recording: true,
        platform: 'darwin',
        settings_deeplinks: {
          accessibility: ACCESSIBILITY_DEEPLINK,
        },
      },
    },
  ],
  server: [],
  repair_actions: [],
};

describe('DoctorDashboard DesktopControl WARN', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockGetRuntimeDoctor.mockResolvedValue(warnDesktopControlDoctor);
  });

  it('renders open-settings button when DesktopControl is warn and deeplink exists', async () => {
    render(<DoctorDashboard />);

    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'desktopOpenSettings' })).toBeInTheDocument();
    });
    expect(screen.getByText('DesktopControl')).toBeInTheDocument();
    expect(screen.getByText('WARN')).toBeInTheDocument();
  });

  it('opens the accessibility deeplink when the settings button is clicked', async () => {
    const windowOpen = vi.spyOn(window, 'open').mockImplementation(() => null);

    render(<DoctorDashboard />);

    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'desktopOpenSettings' })).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole('button', { name: 'desktopOpenSettings' }));

    await waitFor(() => {
      expect(windowOpen).toHaveBeenCalledWith(
        'https://support.apple.com/guide/mac-help/allow-accessibility-apps-to-access-your-mac-mh43185/mac',
        '_blank',
      );
    });

    windowOpen.mockRestore();
  });

  it('does not render open-settings button when deeplink meta is absent', async () => {
    mockGetRuntimeDoctor.mockImplementation(async () => ({
      ...warnDesktopControlDoctor,
      harness: [
        {
          ...warnDesktopControlDoctor.harness[0],
          meta_data: {
            accessibility: false,
            screen_recording: true,
            platform: 'darwin',
            settings_deeplinks: {},
          },
        },
      ],
    }));

    render(<DoctorDashboard />);

    await waitFor(() => {
      expect(screen.getByText('DesktopControl')).toBeInTheDocument();
    });
    expect(screen.queryByRole('button', { name: 'desktopOpenSettings' })).not.toBeInTheDocument();
  });
});
