import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { AppRouterInstance } from 'next/dist/shared/lib/app-router-context.shared-runtime';
import { CLOUD_OAUTH_PENDING_KEY, DESKTOP_OAUTH_TTL_MS, beginDesktopOAuth } from '@/lib/desktop-oauth';
import { IntentDispatcher } from '@/lib/intent-dispatcher';
import { addRemoteProfile, getActiveRemoteProfile, listRemoteProfiles } from '@/lib/remote-profiles';
import useAuthStore from '@/store/useAuthStore';

const mocks = vi.hoisted(() => ({
  switchRemoteFollow: vi.fn<(deferred: boolean) => Promise<void>>(),
  toastError: vi.fn(),
  toastSuccess: vi.fn(),
}));

vi.mock('@/lib/remote-follow-switch', () => ({ switchRemoteFollow: mocks.switchRemoteFollow }));
vi.mock('sonner', () => ({ toast: { error: mocks.toastError, success: mocks.toastSuccess } }));

const CP = 'https://cp.example.com';
const messages = {
  invalidLink: 'invalid',
  oauthSuccess: 'ok',
  oauthFailed: 'failed',
  cloudProfileName: 'Cloud box',
};

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

async function startSignIn(now?: number): Promise<string> {
  const { redirect } = await beginDesktopOAuth(CP, now);
  return new URL(redirect, 'http://local.invalid').searchParams.get('state') ?? '';
}

function callbackLink(exchange: string, state: string): string {
  return `myrmagent://oauth/callback?exchange=${exchange}&state=${state}`;
}

interface CpStub {
  exchange?: Response;
  sandboxes?: Response;
}

/** 控制平面桩：按路径应答，并记录调用顺序。 */
function stubControlPlane({ exchange, sandboxes }: CpStub = {}) {
  const calls: string[] = [];
  const spy = vi.fn(async (input: RequestInfo | URL, _init?: RequestInit) => {
    const url = String(input);
    calls.push(url);
    if (url === `${CP}/api/auth/oauth/exchange`) {
      return (
        exchange ?? Response.json({ token: 'cp-token-abc', user_id: 'u-1', email: 'a@example.com' }, { status: 200 })
      );
    }
    if (url === `${CP}/api/sandboxes`) {
      return sandboxes ?? Response.json({ sandboxes: [{ id: 'sbx-1' }] }, { status: 200 });
    }
    return new Response('unexpected', { status: 500 });
  });
  globalThis.fetch = spy as unknown as typeof fetch;
  return { spy, calls };
}

describe('dispatcher oauth callback', () => {
  const originalWindow = globalThis.window;
  const originalFetch = globalThis.fetch;
  let store: Map<string, string>;
  let pushed: string[];
  let dispatcher: IntentDispatcher;

  beforeEach(() => {
    store = makeWindow();
    pushed = [];
    dispatcher = new IntentDispatcher(mockRouter(pushed), () => undefined, messages);
    useAuthStore.setState({ token: null, isAuthenticated: false });
    mocks.switchRemoteFollow.mockReset().mockResolvedValue(undefined);
    mocks.toastError.mockReset();
    mocks.toastSuccess.mockReset();
  });

  afterEach(() => {
    Object.defineProperty(globalThis, 'window', { configurable: true, value: originalWindow });
    globalThis.fetch = originalFetch;
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it('switches to the cloud connection before persisting the session and a cloud profile', async () => {
    store.set('auth_token', 'local_user_token');
    const { redirect, codeChallenge } = await beginDesktopOAuth(CP);
    const state = new URL(redirect, 'http://local.invalid').searchParams.get('state') ?? '';
    const { calls, spy } = stubControlPlane();
    const atSwitch: { calls: string[]; token: string | null; profiles: number }[] = [];
    mocks.switchRemoteFollow.mockImplementation(async () => {
      atSwitch.push({
        calls: [...calls],
        token: store.get('auth_token') ?? null,
        profiles: listRemoteProfiles().length,
      });
    });

    const ok = await dispatcher.dispatch(callbackLink('ex-1', state));

    expect(ok).toBe(true);
    expect(calls).toEqual([`${CP}/api/auth/oauth/exchange`, `${CP}/api/sandboxes`]);
    const body = JSON.parse(String(spy.mock.calls[0]?.[1]?.body)) as { exchange: string; code_verifier: string };
    expect(body.exchange).toBe('ex-1');
    const digest = new Uint8Array(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(body.code_verifier)));
    expect(Buffer.from(digest).toString('base64url')).toBe(codeChallenge);

    expect(mocks.switchRemoteFollow).toHaveBeenCalledExactlyOnceWith(true);
    expect(atSwitch).toEqual([{ calls, token: 'local_user_token', profiles: 0 }]);
    expect(store.get('myrm-local-auth-token-backup')).toBe('local_user_token');
    expect(useAuthStore.getState().token).toBe('cp-token-abc');
    const active = getActiveRemoteProfile();
    expect(active?.kind).toBe('cloud');
    expect(active?.url).toBe(`${CP}/proxy/me`);
    expect(active?.name).toBe('Cloud box');
    expect(store.has(CLOUD_OAUTH_PENDING_KEY)).toBe(false);
    expect(mocks.toastSuccess).toHaveBeenCalledWith('ok');
    expect(pushed).toEqual(['/settings/system']);
  });

  it('leaves the local session and profiles untouched when the connection switch fails', async () => {
    store.set('auth_token', 'local_user_token');
    const state = await startSignIn();
    stubControlPlane();
    mocks.switchRemoteFollow.mockRejectedValueOnce(new Error('sidecar refused to stop'));

    await dispatcher.dispatch(callbackLink('ex-1', state));

    expect(store.get('auth_token')).toBe('local_user_token');
    expect(store.has('myrm-local-auth-token-backup')).toBe(false);
    expect(useAuthStore.getState().token).toBeNull();
    expect(listRemoteProfiles()).toHaveLength(0);
    expect(mocks.toastError).toHaveBeenCalledWith('failed');
    expect(mocks.toastSuccess).not.toHaveBeenCalled();
    expect(pushed).toEqual(['/settings']);
  });

  it('still ends up with an active cloud profile when the default name is taken', async () => {
    addRemoteProfile('Cloud box', 'https://nuc.example.com');
    const state = await startSignIn();
    stubControlPlane();

    await dispatcher.dispatch(callbackLink('ex-1', state));

    expect(useAuthStore.getState().token).toBe('cp-token-abc');
    expect(getActiveRemoteProfile()).toMatchObject({ kind: 'cloud', name: 'Cloud box 2', url: `${CP}/proxy/me` });
  });

  it('rejects a callback when no sign-in is pending', async () => {
    store.set('auth_token', 'local_user_token');
    const { spy } = stubControlPlane();

    await dispatcher.dispatch(callbackLink('forged-ex', 'forged-state'));

    expect(spy).not.toHaveBeenCalled();
    expect(store.get('auth_token')).toBe('local_user_token');
    expect(useAuthStore.getState().token).toBeNull();
    expect(listRemoteProfiles()).toHaveLength(0);
    expect(pushed).toEqual(['/settings']);
  });

  it('rejects a forged state and keeps the real sign-in alive', async () => {
    const state = await startSignIn();
    const { spy } = stubControlPlane();

    await dispatcher.dispatch(callbackLink('forged-ex', 'forged-state'));

    expect(spy).not.toHaveBeenCalled();
    expect(useAuthStore.getState().token).toBeNull();
    expect(listRemoteProfiles()).toHaveLength(0);

    await dispatcher.dispatch(callbackLink('ex-1', state));
    expect(useAuthStore.getState().token).toBe('cp-token-abc');
  });

  it('rejects a sign-in that outlived its time limit', async () => {
    const state = await startSignIn(Date.now() - DESKTOP_OAUTH_TTL_MS - 1_000);
    const { spy } = stubControlPlane();

    await dispatcher.dispatch(callbackLink('ex-1', state));

    expect(spy).not.toHaveBeenCalled();
    expect(useAuthStore.getState().token).toBeNull();
    expect(store.has(CLOUD_OAUTH_PENDING_KEY)).toBe(false);
  });

  it('refuses a replayed callback', async () => {
    const state = await startSignIn();
    const { spy } = stubControlPlane();

    await dispatcher.dispatch(callbackLink('ex-1', state));
    spy.mockClear();
    useAuthStore.setState({ token: null, isAuthenticated: false });
    await dispatcher.dispatch(callbackLink('ex-1', state));

    expect(spy).not.toHaveBeenCalled();
    expect(useAuthStore.getState().token).toBeNull();
  });

  it('leaves the local session untouched when the exchange is rejected', async () => {
    store.set('auth_token', 'local_user_token');
    const state = await startSignIn();
    const { calls } = stubControlPlane({ exchange: new Response('expired', { status: 400 }) });

    await dispatcher.dispatch(callbackLink('stale-ex', state));

    expect(calls).toEqual([`${CP}/api/auth/oauth/exchange`]);
    expect(mocks.switchRemoteFollow).not.toHaveBeenCalled();
    expect(store.get('auth_token')).toBe('local_user_token');
    expect(useAuthStore.getState().token).toBeNull();
    expect(listRemoteProfiles()).toHaveLength(0);
    expect(store.has(CLOUD_OAUTH_PENDING_KEY)).toBe(false);
    expect(pushed).toEqual(['/settings']);
  });

  it('leaves the local session untouched when the exchange response is incomplete', async () => {
    store.set('auth_token', 'local_user_token');
    const state = await startSignIn();
    const { calls } = stubControlPlane({ exchange: Response.json({ email: 'a@example.com' }, { status: 200 }) });

    await dispatcher.dispatch(callbackLink('ex-1', state));

    expect(calls).toEqual([`${CP}/api/auth/oauth/exchange`]);
    expect(store.get('auth_token')).toBe('local_user_token');
    expect(useAuthStore.getState().token).toBeNull();
  });

  it('leaves the local session untouched when sandbox discovery fails', async () => {
    store.set('auth_token', 'local_user_token');
    const state = await startSignIn();
    stubControlPlane({ sandboxes: new Response('nope', { status: 401 }) });

    await dispatcher.dispatch(callbackLink('ex-1', state));

    expect(mocks.switchRemoteFollow).not.toHaveBeenCalled();
    expect(store.get('auth_token')).toBe('local_user_token');
    expect(useAuthStore.getState().token).toBeNull();
    expect(listRemoteProfiles()).toHaveLength(0);
    expect(pushed).toEqual(['/settings']);
  });

  it('never writes the exchange id or state to the console', async () => {
    const state = await startSignIn();
    stubControlPlane();
    const sinks = [vi.spyOn(console, 'log'), vi.spyOn(console, 'error'), vi.spyOn(console, 'warn')];

    await dispatcher.dispatch(callbackLink('secret-exchange', state));

    const written = sinks
      .flatMap((sink) => sink.mock.calls)
      .map((args) => args.map(String).join(' '))
      .join('\n');
    expect(written).toContain('[UIP]');
    expect(written).not.toContain('secret-exchange');
    expect(written).not.toContain(state);
  });
});
