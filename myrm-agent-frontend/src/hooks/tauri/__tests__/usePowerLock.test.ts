/**
 * [INPUT]
 * - @/hooks/tauri/usePowerLock
 * - @/lib/desktop-bridge::desktopBridge
 * - @/store/useChatStore
 *
 * [OUTPUT]
 * - Unit test suite for usePowerLock desktop power management hook
 *
 * [POS]
 * Verifies acquire/release lifecycle of system power lock during generation on desktop and safe no-op on web.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { usePowerLock } from '../usePowerLock';
import { desktopBridge } from '@/lib/desktop-bridge';
import useChatStore from '@/store/useChatStore';

describe('usePowerLock', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    useChatStore.setState({ loading: false });
  });

  it('does nothing in non-desktop or unsupported environment', async () => {
    const acquireSpy = vi.spyOn(desktopBridge.power, 'acquireLock');
    const releaseSpy = vi.spyOn(desktopBridge.power, 'releaseLock');

    renderHook(() => usePowerLock());

    await act(async () => {
      useChatStore.setState({ loading: true });
    });

    expect(acquireSpy).not.toHaveBeenCalled();
    expect(releaseSpy).not.toHaveBeenCalled();
  });

  it('acquires lock when loading turns true and releases when loading turns false on desktop', async () => {
    // Override getters for desktop testing
    Object.defineProperty(desktopBridge, 'isDesktop', { value: true, configurable: true });
    Object.defineProperty(desktopBridge, 'capabilities', {
      value: { ...desktopBridge.capabilities, hasNativePowerLock: true },
      configurable: true,
    });

    const acquireSpy = vi.spyOn(desktopBridge.power, 'acquireLock').mockResolvedValue('lock-123');
    const releaseSpy = vi.spyOn(desktopBridge.power, 'releaseLock').mockResolvedValue(true);

    renderHook(() => usePowerLock());

    await act(async () => {
      useChatStore.setState({ loading: true });
    });

    expect(acquireSpy).toHaveBeenCalledWith('Agent task in progress');

    await act(async () => {
      useChatStore.setState({ loading: false });
    });

    expect(releaseSpy).toHaveBeenCalledWith('lock-123');
  });
});
