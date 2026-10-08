import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { parseIntentUrl } from '@/lib/intent-dispatcher/schema';
import {
  CLOUD_OAUTH_PENDING_KEY,
  DESKTOP_OAUTH_TTL_MS,
  beginDesktopOAuth,
  buildDesktopDeepLink,
  consumeDesktopOAuth,
  parseDesktopReturn,
  peekDesktopOAuth,
} from '@/lib/desktop-oauth';

function installStorage() {
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

function stateOf(redirect: string): string {
  return new URL(redirect, 'http://local.invalid').searchParams.get('state') ?? '';
}

async function begin(cpBaseUrl: string, now?: number): Promise<string> {
  return stateOf((await beginDesktopOAuth(cpBaseUrl, now)).redirect);
}

/** RFC 7636 S256，独立于实现计算。 */
async function challengeOf(verifier: string): Promise<string> {
  const digest = new Uint8Array(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(verifier)));
  return Buffer.from(digest).toString('base64url');
}

describe('desktop-oauth', () => {
  const originalWindow = globalThis.window;
  let store: Map<string, string>;

  beforeEach(() => {
    store = installStorage();
  });

  afterEach(() => {
    vi.restoreAllMocks();
    Object.defineProperty(globalThis, 'window', { configurable: true, value: originalWindow });
  });

  describe('beginDesktopOAuth', () => {
    it('records the pending sign-in and returns a redirect carrying desktop marker and state', async () => {
      const { redirect } = await beginDesktopOAuth('https://cp.example.com/', 1_000);

      const state = stateOf(redirect);
      expect(redirect.startsWith('/auth/oauth/callback?desktop=1&state=')).toBe(true);
      expect(state).toMatch(/^[0-9a-f]{32}$/);
      expect(JSON.parse(store.get(CLOUD_OAUTH_PENDING_KEY) ?? '{}')).toMatchObject({
        cpBaseUrl: 'https://cp.example.com',
        state,
        createdAt: 1_000,
      });
    });

    it('generates a fresh state per sign-in', async () => {
      const first = await beginDesktopOAuth('https://cp.example.com');
      const second = await beginDesktopOAuth('https://cp.example.com');

      expect(stateOf(first.redirect)).not.toBe(stateOf(second.redirect));
      expect(first.codeChallenge).not.toBe(second.codeChallenge);
    });

    it('returns the S256 challenge of the stored verifier and never the verifier itself', async () => {
      const { redirect, codeChallenge } = await beginDesktopOAuth('https://cp.example.com', 1_000);

      const { codeVerifier } = peekDesktopOAuth(stateOf(redirect), 2_000) ?? { codeVerifier: '' };
      expect(codeVerifier).toMatch(/^[A-Za-z0-9_-]{43}$/);
      expect(codeChallenge).toBe(await challengeOf(codeVerifier));
      expect(codeChallenge).toMatch(/^[A-Za-z0-9_-]{43}$/);
      expect(redirect).not.toContain(codeVerifier);
    });

    it.each(['not a url', 'javascript:alert(1)', 'myrmagent://oauth'])(
      'rejects %s as a control plane address without storing anything',
      async (cpBaseUrl) => {
        await expect(beginDesktopOAuth(cpBaseUrl)).rejects.toThrow();
        expect(store.has(CLOUD_OAUTH_PENDING_KEY)).toBe(false);
      },
    );

    it('stores nothing when SHA-256 is unavailable', async () => {
      vi.spyOn(crypto.subtle, 'digest').mockRejectedValueOnce(new Error('no subtle'));

      await expect(beginDesktopOAuth('https://cp.example.com')).rejects.toThrow('no subtle');
      expect(store.has(CLOUD_OAUTH_PENDING_KEY)).toBe(false);
    });
  });

  describe('peekDesktopOAuth / consumeDesktopOAuth', () => {
    it('returns the control plane address and verifier once for the matching state, then refuses a replay', async () => {
      const state = await begin('https://cp.example.com', 1_000);

      const session = consumeDesktopOAuth(state, 2_000);
      expect(session?.cpBaseUrl).toBe('https://cp.example.com');
      expect(session?.codeVerifier).toMatch(/^[A-Za-z0-9_-]{43}$/);
      expect(store.has(CLOUD_OAUTH_PENDING_KEY)).toBe(false);
      expect(consumeDesktopOAuth(state, 2_001)).toBeNull();
    });

    it('peeks without consuming', async () => {
      const state = await begin('https://cp.example.com', 1_000);

      expect(peekDesktopOAuth(state, 2_000)).toEqual(peekDesktopOAuth(state, 2_001));
      expect(store.has(CLOUD_OAUTH_PENDING_KEY)).toBe(true);
      expect(consumeDesktopOAuth(state, 2_002)).not.toBeNull();
    });

    it('refuses a wrong state without cancelling the real sign-in', async () => {
      const state = await begin('https://cp.example.com', 1_000);

      expect(peekDesktopOAuth('forged', 2_000)).toBeNull();
      expect(consumeDesktopOAuth('forged', 2_000)).toBeNull();
      expect(store.has(CLOUD_OAUTH_PENDING_KEY)).toBe(true);
      expect(consumeDesktopOAuth(state, 2_001)?.cpBaseUrl).toBe('https://cp.example.com');
    });

    it('refuses and drops an expired sign-in, even when only peeking', async () => {
      const state = await begin('https://cp.example.com', 1_000);

      expect(peekDesktopOAuth(state, 1_000 + DESKTOP_OAUTH_TTL_MS + 1)).toBeNull();
      expect(store.has(CLOUD_OAUTH_PENDING_KEY)).toBe(false);
    });

    it('accepts a sign-in right at the TTL boundary', async () => {
      const state = await begin('https://cp.example.com', 1_000);

      expect(consumeDesktopOAuth(state, 1_000 + DESKTOP_OAUTH_TTL_MS)?.cpBaseUrl).toBe('https://cp.example.com');
    });

    it('treats a missing, unreadable or verifier-less record as nothing pending', () => {
      expect(consumeDesktopOAuth('anything')).toBeNull();

      store.set(CLOUD_OAUTH_PENDING_KEY, '{not-json');
      expect(consumeDesktopOAuth('anything')).toBeNull();
      expect(store.has(CLOUD_OAUTH_PENDING_KEY)).toBe(false);

      store.set(CLOUD_OAUTH_PENDING_KEY, JSON.stringify({ cpBaseUrl: 'https://cp.example.com' }));
      expect(consumeDesktopOAuth('anything')).toBeNull();

      store.set(
        CLOUD_OAUTH_PENDING_KEY,
        JSON.stringify({ cpBaseUrl: 'https://cp.example.com', state: 'st', createdAt: Date.now() }),
      );
      expect(consumeDesktopOAuth('st')).toBeNull();
    });

    it('lets a newer sign-in replace the previous one', async () => {
      const first = await begin('https://cp.example.com', 1_000);
      const second = await begin('https://cp.example.com', 1_500);

      expect(consumeDesktopOAuth(first, 2_000)).toBeNull();
      expect(consumeDesktopOAuth(second, 2_000)?.cpBaseUrl).toBe('https://cp.example.com');
    });
  });

  describe('parseDesktopReturn', () => {
    it('reads the state from the redirect value', () => {
      expect(parseDesktopReturn('/auth/oauth/callback?desktop=1&state=abc123')).toEqual({ state: 'abc123' });
    });

    it.each([
      ['no redirect', null],
      ['no desktop marker', '/auth/oauth/callback?state=abc123'],
      ['no state', '/auth/oauth/callback?desktop=1'],
      ['empty state', '/auth/oauth/callback?desktop=1&state='],
      ['another path', '/settings?desktop=1&state=abc123'],
      ['an absolute url', 'https://evil.example/auth/oauth/callback?desktop=1&state=abc123'],
      ['a protocol-relative url', '//evil.example/auth/oauth/callback?desktop=1&state=abc123'],
      ['an oversized state', `/auth/oauth/callback?desktop=1&state=${'a'.repeat(129)}`],
    ])('returns null for %s', (_label, redirect) => {
      expect(parseDesktopReturn(redirect)).toBeNull();
    });
  });

  describe('end-to-end contract', () => {
    it('survives the control plane returning the redirect as a query value', async () => {
      const { redirect } = await beginDesktopOAuth('https://cp.example.com', 1_000);
      // 控制平面把 redirect 当作查询参数值回传：desktop 标记不在顶层。
      const callbackUrl = new URL(
        `https://cp.example.com/auth/oauth/callback?${new URLSearchParams({ exchange: 'ex-1', redirect }).toString()}`,
      );
      expect(callbackUrl.searchParams.get('desktop')).toBeNull();

      const desktopReturn = parseDesktopReturn(callbackUrl.searchParams.get('redirect'));
      expect(desktopReturn).not.toBeNull();

      const link = buildDesktopDeepLink('ex-1', desktopReturn?.state ?? '');
      const intent = parseIntentUrl(link);
      expect(intent).toMatchObject({ action: 'oauth', exchange: 'ex-1', state: stateOf(redirect) });
      expect(consumeDesktopOAuth(stateOf(redirect), 2_000)?.cpBaseUrl).toBe('https://cp.example.com');
    });

    it('url-encodes the exchange id inside the deep link', () => {
      const link = buildDesktopDeepLink('a b&c', 'st');

      expect(link).toBe('myrmagent://oauth/callback?exchange=a+b%26c&state=st');
      expect(parseIntentUrl(link)).toMatchObject({ exchange: 'a b&c', state: 'st' });
    });
  });
});
