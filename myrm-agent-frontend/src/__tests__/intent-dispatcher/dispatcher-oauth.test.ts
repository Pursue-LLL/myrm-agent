import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { AppRouterInstance } from 'next/dist/shared/lib/app-router-context.shared-runtime';
import { IntentDispatcher } from '@/lib/intent-dispatcher';
import { getActiveRemoteProfile, listRemoteProfiles } from '@/lib/remote-profiles';
import useAuthStore from '@/store/useAuthStore';

function mockRouter(pushed: string[]): AppRouterInstance {
  return { push: (url: string) => pushed.push(url) } as unknown as AppRouterInstance;
}

function makeWindow() {
  const store = new Map<string, string>();
  Object.defineProperty(globalThis, 'window', {
    configurable: true,
    value: {
      localStorage: {
        getItem: (k: string) => store.get(k) ?? null,
        setItem: (k: string, v: string) => {
          store.set(k, v);
        },
        removeItem: (k: string) => {
          store.delete(k);
        },
      },
    },
  });
  return store;
}

describe('dispatcher oauth callback', () => {
  const originalWindow = globalThis.window;
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    makeWindow();
    useAuthStore.setState({ token: null, isAuthenticated: false });
  });

  afterEach(() => {
    Object.defineProperty(globalThis, 'window', { configurable: true, value: originalWindow });
    globalThis.fetch = originalFetch;
    vi.unstubAllGlobals();
  });

  it('persists token and creates cloud profile when sandbox discovery succeeds', async () => {
    const store = makeWindow();
    store.set('myrm-cloud-oauth-pending', JSON.stringify({ cpBaseUrl: 'https://cp.example.com' }));
    globalThis.fetch = vi.fn(async () =>
      Response.json({ sandboxes: [{ id: 'sbx-1' }] }, { status: 200 }),
    ) as unknown as typeof fetch;

    const pushed: string[] = [];
    const dispatcher = new IntentDispatcher(mockRouter(pushed), () => undefined);
    const ok = await dispatcher.dispatch('myrmagent://oauth/callback?token=cp-token-abc');
    expect(ok).toBe(true);
    expect(useAuthStore.getState().token).toBe('cp-token-abc');
    const active = getActiveRemoteProfile();
    expect(active?.kind).toBe('cloud');
    expect(active?.url).toBe('https://cp.example.com/proxy/me');
    expect(listRemoteProfiles()).toHaveLength(1);
    expect(pushed).toEqual(['/settings']);
  });

  it('leaves local session untouched when discovery fails', async () => {
    const store = makeWindow();
    store.set('auth_token', 'local_user_token');
    store.set('myrm-cloud-oauth-pending', JSON.stringify({ cpBaseUrl: 'https://cp.example.com' }));
    globalThis.fetch = vi.fn(async () => new Response('nope', { status: 401 })) as unknown as typeof fetch;

    const pushed: string[] = [];
    const dispatcher = new IntentDispatcher(mockRouter(pushed), () => undefined);
    const ok = await dispatcher.dispatch('myrmagent://oauth/callback?token=bad-token');
    expect(ok).toBe(true);
    expect(store.get('auth_token')).toBe('local_user_token');
    expect(listRemoteProfiles()).toHaveLength(0);
    expect(pushed).toEqual(['/settings']);
  });
});
