import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

type Listener = (key: string, value: { localApiKey: string } | null, meta: unknown) => void;

const manager = vi.hoisted(() => ({
  get: vi.fn(),
  set: vi.fn(),
  ensureKeyLoaded: vi.fn(),
  subscribe: vi.fn(),
}));

vi.mock('@/services/config', () => ({
  getConfigSyncManager: () => manager,
}));

type HookModule = typeof import('@/hooks/settings/usePrivacyRoutingSecret');

describe('usePrivacyRoutingSecret', () => {
  let usePrivacyRoutingSecret: HookModule['usePrivacyRoutingSecret'];
  let listener: Listener | null;
  const unsubscribe = vi.fn();

  beforeEach(async () => {
    vi.resetModules();
    listener = null;
    unsubscribe.mockReset();
    manager.get.mockReset().mockReturnValue(null);
    manager.set.mockReset();
    manager.ensureKeyLoaded.mockReset().mockResolvedValue(undefined);
    manager.subscribe.mockReset().mockImplementation((_key: string, next: Listener) => {
      listener = next;
      return unsubscribe;
    });
    ({ usePrivacyRoutingSecret } = await import('@/hooks/settings/usePrivacyRoutingSecret'));
  });

  it('starts empty and shows the saved key once its row is synced', async () => {
    manager.get.mockReturnValue({ localApiKey: 'sk-saved' });

    const { result } = renderHook(() => usePrivacyRoutingSecret());

    expect(result.current[0]).toBe('');
    await waitFor(() => expect(result.current[0]).toBe('sk-saved'));
  });

  it('writes what the user types to the secret row', async () => {
    const { result } = renderHook(() => usePrivacyRoutingSecret());
    await waitFor(() => expect(manager.ensureKeyLoaded).toHaveBeenCalled());

    act(() => result.current[1]('sk-typed'));

    expect(result.current[0]).toBe('sk-typed');
    expect(manager.set).toHaveBeenCalledWith('privacyRoutingSecret', { localApiKey: 'sk-typed' });
  });

  it('does not overwrite what the user typed while the row was still loading', async () => {
    let finishLoad: () => void = () => {};
    manager.ensureKeyLoaded.mockReturnValue(new Promise<void>((resolve) => (finishLoad = resolve)));
    manager.get.mockReturnValue({ localApiKey: 'sk-saved' });
    const { result } = renderHook(() => usePrivacyRoutingSecret());

    act(() => result.current[1]('sk-typed-first'));
    await act(async () => {
      finishLoad();
    });

    expect(result.current[0]).toBe('sk-typed-first');
  });

  it('follows changes made elsewhere and stops listening on unmount', async () => {
    const { result, unmount } = renderHook(() => usePrivacyRoutingSecret());
    await waitFor(() => expect(listener).not.toBeNull());

    act(() => listener?.('privacyRoutingSecret', { localApiKey: 'sk-from-another-tab' }, {}));
    expect(result.current[0]).toBe('sk-from-another-tab');

    unmount();
    expect(unsubscribe).toHaveBeenCalledTimes(1);
  });
});
