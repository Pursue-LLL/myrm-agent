/**
 * @vitest-environment jsdom
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, waitFor, screen, fireEvent } from '@testing-library/react';
import { toast } from 'sonner';

import { UpdateHandoffNotifier } from '../update-handoff-notifier';
import * as deployMode from '@/lib/deploy-mode';
import * as updateHandoffHook from '@/hooks/tauri/useUpdateHandoff';
import * as appUpdateHook from '@/hooks/tauri/useAppUpdate';

// Stable next-intl mock
const stableT = (key: string, params?: Record<string, unknown>) => {
  if (params) {
    return `${key}:${JSON.stringify(params)}`;
  }
  return key;
};

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

vi.mock('sonner', () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
  },
}));

describe('UpdateHandoffNotifier Component', () => {
  const mockCheck = vi.fn();
  const mockDismiss = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
    vi.spyOn(deployMode, 'isTauriRuntime').mockReturnValue(true);
    vi.spyOn(appUpdateHook, 'useAppUpdate').mockReturnValue({
      status: 'idle',
      error: null,
      updateInfo: null,
      progress: null,
      check: mockCheck,
      install: vi.fn(),
      dismiss: vi.fn(),
      clearError: vi.fn(),
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('renders nothing in non-Tauri runtime', () => {
    vi.spyOn(deployMode, 'isTauriRuntime').mockReturnValue(false);
    vi.spyOn(updateHandoffHook, 'useUpdateHandoff').mockReturnValue({
      result: {
        type: 'success',
        fromVersion: '0.1.39',
        targetVersion: '0.1.40',
        currentVersion: '0.1.40',
      },
      dismiss: mockDismiss,
    });

    const { container } = render(<UpdateHandoffNotifier />);
    expect(container.firstChild).toBeNull();
    expect(toast.success).not.toHaveBeenCalled();
    expect(toast.error).not.toHaveBeenCalled();
  });

  it('renders nothing when there is no handoff result', () => {
    vi.spyOn(updateHandoffHook, 'useUpdateHandoff').mockReturnValue({
      result: null,
      dismiss: mockDismiss,
    });

    const { container } = render(<UpdateHandoffNotifier />);
    expect(container.firstChild).toBeNull();
    expect(toast.success).not.toHaveBeenCalled();
    expect(toast.error).not.toHaveBeenCalled();
  });

  it('displays success toast and calls dismiss when update succeeded', async () => {
    vi.spyOn(updateHandoffHook, 'useUpdateHandoff').mockReturnValue({
      result: {
        type: 'success',
        fromVersion: '0.1.39',
        targetVersion: '0.1.40',
        currentVersion: '0.1.40',
      },
      dismiss: mockDismiss,
    });

    render(<UpdateHandoffNotifier />);

    await waitFor(() => {
      expect(toast.success).toHaveBeenCalledTimes(1);
    });

    expect(toast.success).toHaveBeenCalledWith(
      'handoffSuccessTitle',
      expect.objectContaining({
        duration: 6000,
      }),
    );
    expect(mockDismiss).toHaveBeenCalledTimes(1);
    expect(toast.error).not.toHaveBeenCalled();
  });

  it('displays error toast with retry action when update failed', async () => {
    vi.spyOn(updateHandoffHook, 'useUpdateHandoff').mockReturnValue({
      result: {
        type: 'failure',
        fromVersion: '0.1.39',
        targetVersion: '0.1.40',
        currentVersion: '0.1.39',
      },
      dismiss: mockDismiss,
    });

    render(<UpdateHandoffNotifier />);

    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledTimes(1);
    });

    expect(toast.error).toHaveBeenCalledWith(
      'handoffFailureTitle',
      expect.objectContaining({
        duration: 10000,
        action: expect.objectContaining({
          label: 'retry',
          onClick: expect.any(Function),
        }),
      }),
    );

    // Test clicking retry action calls check()
    const errorCallArgs = (toast.error as unknown as { mock: { calls: unknown[][] } }).mock.calls[0];
    const options = errorCallArgs[1] as { action?: { onClick?: () => void } };
    options.action?.onClick?.();
    expect(mockCheck).toHaveBeenCalledTimes(1);

    expect(mockDismiss).toHaveBeenCalledTimes(1);
    expect(toast.success).not.toHaveBeenCalled();
  });
});
