/**
 * [INPUT]
 * - @/hooks/tauri/useDesktopWakeRecovery::useDesktopWakeRecovery
 * - @/services/desktopWakeRecovery::setupDesktopWakeRecovery
 *
 * [OUTPUT]
 * - Integration test suite for useDesktopWakeRecovery hook lifecycle
 *
 * [POS]
 * Verifies mount subscription and unmount cleanup lifecycle for desktop wake recovery.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook } from '@testing-library/react';
import { useDesktopWakeRecovery } from '../useDesktopWakeRecovery';
import * as desktopWakeService from '@/services/desktopWakeRecovery';

describe('useDesktopWakeRecovery integration', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('subscribes on mount and invokes unlisten on unmount', async () => {
    const unlistenMock = vi.fn();
    const setupSpy = vi.spyOn(desktopWakeService, 'setupDesktopWakeRecovery').mockResolvedValue(unlistenMock);

    const { unmount } = renderHook(() => useDesktopWakeRecovery());

    expect(setupSpy).toHaveBeenCalledTimes(1);

    // 等待微任务队列排空，确保 setupDesktopWakeRecovery promise 完成
    await Promise.resolve();

    unmount();

    expect(unlistenMock).toHaveBeenCalledTimes(1);
  });

  it('handles immediate unmount before setupDesktopWakeRecovery resolves cleanly', async () => {
    let resolveSetup: ((fn: () => void) => void) | undefined;
    const unlistenMock = vi.fn();
    const delayedPromise = new Promise<() => void>((resolve) => {
      resolveSetup = resolve;
    });

    vi.spyOn(desktopWakeService, 'setupDesktopWakeRecovery').mockReturnValue(delayedPromise);

    const { unmount } = renderHook(() => useDesktopWakeRecovery());

    unmount();

    // 延迟 resolve 后不崩溃
    if (resolveSetup) {
      resolveSetup(unlistenMock);
    }
    await Promise.resolve();

    expect(unlistenMock).not.toHaveBeenCalled();
  });
});
