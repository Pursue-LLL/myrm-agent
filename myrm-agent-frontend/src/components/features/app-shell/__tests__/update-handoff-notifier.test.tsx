/**
 * @vitest-environment jsdom
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, waitFor, act } from '@testing-library/react';
import { toast } from 'sonner';

import { UpdateHandoffNotifier } from '../update-handoff-notifier';
import { isTauriRuntime } from '@/lib/deploy-mode';
import { useUpdateHandoff } from '@/hooks/tauri/useUpdateHandoff';
import { useAppUpdate } from '@/hooks/tauri/useAppUpdate';

const stableT = (key: string, params?: Record<string, unknown>) => {
  if (params) {
    let res = key;
    for (const [k, v] of Object.entries(params)) {
      res += `:${k}=${v}`;
    }
    return res;
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
    info: vi.fn(),
    warning: vi.fn(),
  },
}));

vi.mock('@/lib/deploy-mode', () => ({
  isTauriRuntime: vi.fn(),
}));

vi.mock('@/hooks/tauri/useUpdateHandoff', () => ({
  useUpdateHandoff: vi.fn(),
}));

vi.mock('@/hooks/tauri/useAppUpdate', () => ({
  useAppUpdate: vi.fn(),
}));

describe('UpdateHandoffNotifier Component', () => {
  const mockCheck = vi.fn();
  const mockDismiss = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(useAppUpdate).mockReturnValue({
      check: mockCheck,
    } as unknown as ReturnType<typeof useAppUpdate>);
  });

  it('renders nothing in non-Tauri runtime', () => {
    vi.mocked(isTauriRuntime).mockReturnValue(false);
    vi.mocked(useUpdateHandoff).mockReturnValue({
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
    expect(mockDismiss).not.toHaveBeenCalled();
  });

  it('triggers toast.success and dismiss when update succeeded in Tauri runtime', async () => {
    vi.mocked(isTauriRuntime).mockReturnValue(true);
    vi.mocked(useUpdateHandoff).mockReturnValue({
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
        description: 'handoffSuccessDescription:version=0.1.40:fromVersion=0.1.39',
        duration: 6000,
      }),
    );
    expect(mockDismiss).toHaveBeenCalledTimes(1);
  });

  it('triggers toast.error with retry action when update failed in Tauri runtime', async () => {
    vi.mocked(isTauriRuntime).mockReturnValue(true);
    vi.mocked(useUpdateHandoff).mockReturnValue({
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
        description: 'handoffFailureDescription:currentVersion=0.1.39:targetVersion=0.1.40',
        duration: 10000,
        action: expect.objectContaining({
          label: 'retry',
        }),
      }),
    );
    expect(mockDismiss).toHaveBeenCalledTimes(1);

    // Test retry action invocation
    const errorCall = vi.mocked(toast.error).mock.calls[0];
    const actionConfig = errorCall[1]?.action as { label: string; onClick: () => void };
    expect(actionConfig).toBeDefined();

    act(() => {
      actionConfig.onClick();
    });

    expect(mockCheck).toHaveBeenCalledTimes(1);
  });

  it('does nothing when result is null', () => {
    vi.mocked(isTauriRuntime).mockReturnValue(true);
    vi.mocked(useUpdateHandoff).mockReturnValue({
      result: null,
      dismiss: mockDismiss,
    });

    render(<UpdateHandoffNotifier />);

    expect(toast.success).not.toHaveBeenCalled();
    expect(toast.error).not.toHaveBeenCalled();
    expect(mockDismiss).not.toHaveBeenCalled();
  });
});
