import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';

const mockGet = vi.fn();
const mockSet = vi.fn();

vi.mock('@/services/config', () => ({
  getConfigSyncManager: () => ({
    get: (...args: unknown[]) => mockGet(...args),
    set: (...args: unknown[]) => mockSet(...args),
  }),
}));

vi.mock('@/lib/deploy-mode', () => ({
  isTauriRuntime: () => false,
}));

const mockFetch = vi.fn();

describe('useManagedPolicyEffective', () => {
  beforeEach(() => {
    mockFetch.mockReset();
    mockGet.mockReset();
    mockSet.mockReset();
    vi.stubGlobal('fetch', mockFetch);
    Object.defineProperty(document, 'visibilityState', {
      configurable: true,
      value: 'visible',
    });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.resetModules();
  });

  async function loadHook() {
    const { useManagedPolicyEffective } = await import('@/hooks/useManagedPolicyEffective');
    return renderHook(() => useManagedPolicyEffective());
  }

  it('fetches effective MAP on mount', async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: async () => ({
        active: true,
        disableYolo: false,
        disableAllowAlways: false,
        forceAutoReviewForModels: ['gpt-4o'],
        ignoreAllowlistForModels: [],
      }),
    });

    const { result } = await loadHook();

    await waitFor(() => {
      expect(result.current.loaded).toBe(true);
    });

    expect(mockFetch).toHaveBeenCalledTimes(1);
    expect(result.current.active).toBe(true);
    expect(result.current.policy.forceAutoReviewForModels).toEqual(['gpt-4o']);
  });

  it('refetches when tab becomes visible again', async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: async () => ({ active: false }),
    });

    await loadHook();

    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalledTimes(1);
    });

    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        active: true,
        disableYolo: false,
        forceAutoReviewForModels: ['claude-opus-4'],
        ignoreAllowlistForModels: [],
      }),
    });

    Object.defineProperty(document, 'visibilityState', {
      configurable: true,
      value: 'hidden',
    });
    act(() => {
      document.dispatchEvent(new Event('visibilitychange'));
    });
    expect(mockFetch).toHaveBeenCalledTimes(1);

    Object.defineProperty(document, 'visibilityState', {
      configurable: true,
      value: 'visible',
    });
    act(() => {
      document.dispatchEvent(new Event('visibilitychange'));
    });

    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalledTimes(2);
    });
  });

  it('clears stale YOLO after refetch when org disables YOLO', async () => {
    mockGet.mockReturnValue({ yoloModeEnabled: true, yoloModeTimeout: 3600, yoloModeEnabledAt: 1 });
    mockFetch.mockResolvedValue({
      ok: true,
      json: async () => ({
        active: true,
        disableYolo: true,
        disableAllowAlways: false,
        forceAutoReviewForModels: [],
        ignoreAllowlistForModels: [],
        revision: 2,
      }),
    });

    await loadHook();

    await waitFor(() => {
      expect(mockSet).toHaveBeenCalledWith(
        'securityConfig',
        expect.objectContaining({ yoloModeEnabled: false }),
      );
    });
  });

  it('refetches when managed policy updated event fires', async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: async () => ({ active: false, revision: 1 }),
    });

    await loadHook();

    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalledTimes(1);
    });

    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        active: true,
        disableYolo: true,
        revision: 2,
      }),
    });

    const { MANAGED_POLICY_UPDATED_EVENT } = await import('@/lib/managedPolicyEffectiveEvents');
    act(() => {
      window.dispatchEvent(
        new CustomEvent(MANAGED_POLICY_UPDATED_EVENT, { detail: { revision: 2, active: true } }),
      );
    });

    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalledTimes(2);
    });
  });

  it('skips refetch when SSE revision is not newer than last applied', async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: async () => ({ active: true, revision: 3 }),
    });

    await loadHook();

    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalledTimes(1);
    });

    const { MANAGED_POLICY_UPDATED_EVENT } = await import('@/lib/managedPolicyEffectiveEvents');
    act(() => {
      window.dispatchEvent(
        new CustomEvent(MANAGED_POLICY_UPDATED_EVENT, { detail: { revision: 2, active: true } }),
      );
    });

    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 20));
    });

    expect(mockFetch).toHaveBeenCalledTimes(1);
  });

  it('dedupes concurrent effective MAP fetches across hook instances', async () => {
    let resolveJson: (value: unknown) => void = () => undefined;
    mockFetch.mockImplementation(
      () =>
        new Promise((resolve) => {
          resolveJson = (value) =>
            resolve({
              ok: true,
              json: async () => value,
            });
        }),
    );

    const { useManagedPolicyEffective } = await import('@/hooks/useManagedPolicyEffective');
    renderHook(() => useManagedPolicyEffective());
    renderHook(() => useManagedPolicyEffective());

    expect(mockFetch).toHaveBeenCalledTimes(1);

    resolveJson({ active: false });

    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalledTimes(1);
    });
  });
});
