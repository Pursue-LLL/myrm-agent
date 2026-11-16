/** @vitest-environment jsdom */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { renderHook } from '@testing-library/react';

const connect = vi.fn();
const disconnect = vi.fn();

vi.mock('@/services/ConnectionManager', () => ({
  connectionManager: { connect: () => connect(), disconnect: () => disconnect() },
}));

vi.mock('@/store/useAuthStore', () => ({
  default: (select: (state: { isAuthenticated: boolean }) => boolean) => select({ isAuthenticated: true }),
}));

vi.mock('@/lib/deploy-mode', () => ({ resolveE2eApiBase: () => 'http://127.0.0.1:18080' }));

import { useWorkspaceStream } from '@/hooks/workspace/useWorkspaceStream';

const E2E_POLL_MS = 1500;

describe('useWorkspaceStream', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllEnvs();
    vi.clearAllMocks();
  });

  it('connects once and disconnects on unmount', () => {
    const { unmount } = renderHook(() => useWorkspaceStream());
    expect(connect).toHaveBeenCalledTimes(1);

    unmount();
    expect(disconnect).toHaveBeenCalledTimes(1);
  });

  it('follows an E2E binding by polling and on the runtime-ready event outside production', () => {
    const { unmount } = renderHook(() => useWorkspaceStream());

    vi.advanceTimersByTime(E2E_POLL_MS);
    expect(connect).toHaveBeenCalledTimes(2);

    window.dispatchEvent(new CustomEvent('myrm_e2e_runtime_ready'));
    expect(connect).toHaveBeenCalledTimes(3);

    unmount();
    vi.advanceTimersByTime(E2E_POLL_MS * 2);
    window.dispatchEvent(new CustomEvent('myrm_e2e_runtime_ready'));
    expect(connect).toHaveBeenCalledTimes(3);
  });

  it('neither polls nor listens for the E2E binding in a production build', () => {
    vi.stubEnv('NODE_ENV', 'production');
    const { unmount } = renderHook(() => useWorkspaceStream());

    vi.advanceTimersByTime(E2E_POLL_MS * 3);
    window.dispatchEvent(new CustomEvent('myrm_e2e_runtime_ready'));
    expect(connect).toHaveBeenCalledTimes(1);
    expect(vi.getTimerCount()).toBe(0);

    unmount();
    expect(disconnect).toHaveBeenCalledTimes(1);
  });
});
