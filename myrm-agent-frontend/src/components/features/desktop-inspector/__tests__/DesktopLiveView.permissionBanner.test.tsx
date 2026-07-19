/** @vitest-environment jsdom */
'use client';

import { render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import DesktopLiveView from '../DesktopLiveView';

const mockApiRequest = vi.fn();

vi.mock('next-intl', () => ({
  useTranslations: () => (key: string) => key,
}));

vi.mock('@/lib/api', () => ({
  apiRequest: (...args: unknown[]) => mockApiRequest(...args),
}));

vi.mock('@/store/useDesktopInspectorStore', () => ({
  default: () => ({
    isOpen: true,
    mode: 'view',
    viewData: {
      needsPermission: true,
      screenshotBase64: '',
      mimeType: 'image/png',
      refs: {},
      appName: 'TextEdit',
      windowTitle: 'Untitled',
      scope: 'app',
      viewportWidth: 800,
      viewportHeight: 600,
      updatedAt: Date.now(),
    },
    selectedElement: null,
    instructionText: '',
    closePanel: vi.fn(),
    setMode: vi.fn(),
    selectElement: vi.fn(),
    clearSelection: vi.fn(),
    setInstructionText: vi.fn(),
    fetchSnapshot: vi.fn(),
    isSnapshotLoading: false,
  }),
}));

describe('DesktopLiveView PermissionBanner', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('shows check-failed banner when permissions API is unavailable', async () => {
    mockApiRequest.mockRejectedValueOnce(new Error('network'));

    render(<DesktopLiveView onSendInstruction={vi.fn()} />);

    await waitFor(() => {
      expect(screen.getByText('permissionCheckFailed')).toBeInTheDocument();
    });
    expect(screen.queryByText('permissionDenied')).not.toBeInTheDocument();
    expect(screen.getByText('permissionCheckAgain')).toBeInTheDocument();
  });

  it('shows missing-permission details when permissions API succeeds', async () => {
    mockApiRequest.mockResolvedValueOnce({
      accessibility: false,
      screen_recording: true,
      all_granted: false,
      platform: 'darwin',
      settings_deeplinks: {},
    });

    render(<DesktopLiveView onSendInstruction={vi.fn()} />);

    await waitFor(() => {
      expect(screen.getByText('permissionDeniedAccessibility')).toBeInTheDocument();
    });
    expect(screen.queryByText('permissionCheckFailed')).not.toBeInTheDocument();
  });
});
