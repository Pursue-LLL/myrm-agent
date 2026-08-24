/**
 * @vitest-environment jsdom
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render } from '@testing-library/react';
import { UpdateHandoffNotifier } from '../update-handoff-notifier';
import * as deployMode from '@/lib/deploy-mode';
import * as handoffHook from '@/hooks/tauri/useUpdateHandoff';
import * as appUpdateHook from '@/hooks/tauri/useAppUpdate';
import { toast } from 'sonner';

const stableT = (key: string, params?: Record<string, unknown>) => {
  if (params) {
    let res = key;
    for (const [k, v] of Object.entries(params)) {
      res += `:${k}=${String(v)}`;
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
  },
}));

describe('UpdateHandoffNotifier component', () => {
  const mockDismiss = vi.fn();
  const mockCheck = vi.fn().mockResolvedValue(undefined);

  beforeEach(() => {
    vi.clearAllMocks();
    vi.spyOn(deployMode, 'isTauriRuntime').mockReturnValue(true);
    vi.spyOn(appUpdateHook, 'useAppUpdate').mockReturnValue({
      state: 'idle',
      updateInfo: null,
      progress: null,
      error: null,
      check: mockCheck,
      downloadAndInstall: vi.fn(),
      dismiss: vi.fn(),
      setDismissed: vi.fn(),
    });
  });

  it('does nothing when not in Tauri runtime', () => {
    vi.spyOn(deployMode, 'isTauriRuntime').mockReturnValue(false);
    vi.spyOn(handoffHook, 'useUpdateHandoff').mockReturnValue({
      result: {
        type: 'success',
        fromVersion: '0.1.0',
        currentVersion: '0.2.0',
      },
      dismiss: mockDismiss,
    });

    render(<UpdateHandoffNotifier />);

    expect(toast.success).not.toHaveBeenCalled();
    expect(toast.error).not.toHaveBeenCalled();
    expect(mockDismiss).not.toHaveBeenCalled();
  });

  it('does nothing when result is null', () => {
    vi.spyOn(handoffHook, 'useUpdateHandoff').mockReturnValue({
      result: null,
      dismiss: mockDismiss,
    });

    render(<UpdateHandoffNotifier />);

    expect(toast.success).not.toHaveBeenCalled();
    expect(toast.error).not.toHaveBeenCalled();
    expect(mockDismiss).not.toHaveBeenCalled();
  });

  it('triggers success toast and dismisses when result is success', () => {
    vi.spyOn(handoffHook, 'useUpdateHandoff').mockReturnValue({
      result: {
        type: 'success',
        fromVersion: '0.1.0',
        currentVersion: '0.2.0',
      },
      dismiss: mockDismiss,
    });

    render(<UpdateHandoffNotifier />);

    expect(toast.success).toHaveBeenCalledWith(
      'handoffSuccessTitle',
      expect.objectContaining({
        description: 'handoffSuccessDescription:version=0.2.0:fromVersion=0.1.0',
        duration: 6000,
      }),
    );
    expect(mockDismiss).toHaveBeenCalledTimes(1);
  });

  it('triggers error toast with retry action when result is failure', () => {
    vi.spyOn(handoffHook, 'useUpdateHandoff').mockReturnValue({
      result: {
        type: 'failure',
        targetVersion: '0.3.0',
        currentVersion: '0.1.0',
      },
      dismiss: mockDismiss,
    });

    render(<UpdateHandoffNotifier />);

    expect(toast.error).toHaveBeenCalledWith(
      'handoffFailureTitle',
      expect.objectContaining({
        description: 'handoffFailureDescription:currentVersion=0.1.0:targetVersion=0.3.0',
        duration: 10000,
        action: expect.objectContaining({
          label: 'retry',
        }),
      }),
    );
    expect(mockDismiss).toHaveBeenCalledTimes(1);

    // Test clicking retry action
    const errorCall = vi.mocked(toast.error).mock.calls[0];
    const options = errorCall[1] as { action: { onClick: () => void } };
    options.action.onClick();
    expect(mockCheck).toHaveBeenCalledTimes(1);
  });
});
