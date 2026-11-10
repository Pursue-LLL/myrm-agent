import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { deferred } from '@/test-utils/deferred';

import {
  getMobilePairToken,
  isMobileRemoteSurface,
  refreshMobilePairToken,
  scheduleMobilePairRefresh,
  storeMobilePairToken,
} from '../mobileRemote';
import { BACKEND, jsonResponse, kit, NOW, pairToken, tokenExpiringIn } from './mobileRemoteKit';

vi.mock('@/lib/e2ee/client', async () => (await import('./mobileRemoteKit')).e2eeClientMock());
vi.mock('@/lib/utils/apiConfig', async () => (await import('./mobileRemoteKit')).apiConfigMock());

const STORAGE_KEY = 'mobile_pair_token';
const REFRESH_URL = `${BACKEND}/api/v1/remote-access/pairing-token/refresh`;
const MINUTE = 60_000;
const DAY = 24 * 60 * MINUTE;
const MIN_DELAY = 30_000;

const fetchMock = vi.fn<typeof fetch>();

const stored = () => sessionStorage.getItem(STORAGE_KEY);
const address = () => window.location.pathname + window.location.search + window.location.hash;
const goTo = (url: string) => window.history.replaceState(null, '', url);

beforeEach(() => {
  vi.resetAllMocks();
  sessionStorage.clear();
  goTo('/mobile');
  kit.loadStoredE2EESession.mockReturnValue(null);
  vi.stubGlobal('fetch', fetchMock);
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe('isMobileRemoteSurface', () => {
  it.each([
    ['/mobile', true],
    ['/mobile/takeover/c1', true],
    ['/', false],
    ['/mobile-app', false],
  ])('is decided by the current page: %s -> %s', (path, expected) => {
    goTo(path);

    expect(isMobileRemoteSurface()).toBe(expected);
  });

  it('is never the surface without a window', () => {
    vi.stubGlobal('window', undefined);

    expect(isMobileRemoteSurface()).toBe(false);
  });
});

describe('getMobilePairToken', () => {
  it('has no token before a phone was paired', () => {
    expect(getMobilePairToken()).toBeUndefined();
  });

  it('takes the token from the address, keeps it for this tab and removes it from the address', () => {
    goTo('/mobile/status/c1?view=live&pair=tok#top');
    const entries = window.history.length;

    expect(getMobilePairToken()).toBe('tok');

    expect(stored()).toBe('tok');
    expect(address()).toBe('/mobile/status/c1?view=live#top');
    expect(window.history.length).toBe(entries);
  });

  it('leaves a bare path when the token was the only parameter', () => {
    goTo('/mobile?pair=tok');

    getMobilePairToken();

    expect(address()).toBe('/mobile');
  });

  it('keeps asking the stored token once the address no longer carries it', () => {
    goTo('/mobile?pair=tok');
    getMobilePairToken();

    expect(getMobilePairToken()).toBe('tok');
    expect(getMobilePairToken()).toBe('tok');
  });

  it('prefers the token in the address over the stored one and replaces it', () => {
    storeMobilePairToken('old');
    goTo('/mobile?pair=new');

    expect(getMobilePairToken()).toBe('new');
    expect(stored()).toBe('new');
  });

  it('falls back to the stored token and leaves the address alone', () => {
    storeMobilePairToken('stored-token');
    goTo('/mobile?view=live');

    expect(getMobilePairToken()).toBe('stored-token');
    expect(address()).toBe('/mobile?view=live');
  });

  it('ignores an empty token in the address', () => {
    storeMobilePairToken('stored-token');
    goTo('/mobile?pair=');

    expect(getMobilePairToken()).toBe('stored-token');
    expect(address()).toBe('/mobile?pair=');
  });

  it('has no token without a window', () => {
    storeMobilePairToken('stored-token');
    vi.stubGlobal('window', undefined);

    expect(getMobilePairToken()).toBeUndefined();
  });
});

describe('storeMobilePairToken', () => {
  it('keeps the token for this tab only', () => {
    storeMobilePairToken('tok');

    expect(stored()).toBe('tok');
    expect(localStorage.length).toBe(0);
  });

  it('does nothing without a window', () => {
    vi.stubGlobal('window', undefined);

    storeMobilePairToken('tok');

    expect(stored()).toBeNull();
  });
});

describe('refreshMobilePairToken', () => {
  it('asks for nothing while no phone is paired', async () => {
    await expect(refreshMobilePairToken()).resolves.toBeUndefined();

    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('posts to the renewal endpoint with the current token, then keeps and returns the new one', async () => {
    storeMobilePairToken('old');
    fetchMock.mockResolvedValue(jsonResponse({ success: true, data: { token: 'fresh', mobilePath: '/mobile' } }));

    await expect(refreshMobilePairToken()).resolves.toBe('fresh');

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe(REFRESH_URL);
    expect(init?.method).toBe('POST');
    expect(init?.headers).toMatchObject({ 'X-Pair-Token': 'old' });
    expect(stored()).toBe('fresh');
  });

  it('keeps the current token when the answer carries no new one', async () => {
    storeMobilePairToken('old');
    fetchMock.mockResolvedValue(jsonResponse({ success: true, data: {} }));

    await expect(refreshMobilePairToken()).resolves.toBeUndefined();

    expect(stored()).toBe('old');
  });

  it('keeps the current token and reports the failure when the server refuses', async () => {
    storeMobilePairToken('old');
    fetchMock.mockResolvedValue(jsonResponse({ detail: 'expired' }, 401));

    await expect(refreshMobilePairToken()).rejects.toThrow('Mobile API failed: 401');

    expect(stored()).toBe('old');
  });
});

describe('scheduleMobilePairRefresh', () => {
  beforeEach(() => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout', 'Date'], now: NOW });
  });

  const start = (token: string) => {
    storeMobilePairToken(token);
    return scheduleMobilePairRefresh();
  };

  /** Every renewal answers with a token that is valid for two more hours. */
  const renewForTwoHours = () =>
    fetchMock.mockImplementation(() => Promise.resolve(jsonResponse({ data: { token: tokenExpiringIn(7200) } })));

  it('does nothing without a window and can still be stopped', () => {
    vi.stubGlobal('window', undefined);

    const stop = scheduleMobilePairRefresh();

    expect(() => stop()).not.toThrow();
    expect(vi.getTimerCount()).toBe(0);
  });

  it('waits while no phone is paired', () => {
    scheduleMobilePairRefresh();

    expect(vi.getTimerCount()).toBe(0);
  });

  it.each([
    ['garbage', 'not-a-token'],
    ['an empty body', '.sig'],
    ['no expiry', pairToken({ purpose: 'pair' })],
    ['a zero expiry', pairToken({ exp: 0 })],
  ])('does not schedule anything for a token with %s', (_name, token) => {
    start(token);

    expect(vi.getTimerCount()).toBe(0);
  });

  it('reads tokens whose payload needs the URL-safe alphabet', async () => {
    renewForTwoHours();
    start(pairToken({ chat_id: '>>>???', exp: NOW / 1000 + 3600 }));

    await vi.advanceTimersByTimeAsync(55 * MINUTE);

    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it('renews five minutes before the token expires', async () => {
    renewForTwoHours();
    start(tokenExpiringIn(3600));

    await vi.advanceTimersByTimeAsync(55 * MINUTE - 1);
    expect(fetchMock).not.toHaveBeenCalled();
    await vi.advanceTimersByTimeAsync(1);

    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock.mock.calls[0][0]).toBe(REFRESH_URL);
  });

  it.each([
    ['about to expire', 60],
    ['already expired', -3600],
  ])('waits at least 30 seconds for a token that is %s', async (_name, seconds) => {
    renewForTwoHours();
    start(tokenExpiringIn(seconds));

    await vi.advanceTimersByTimeAsync(MIN_DELAY - 1);
    expect(fetchMock).not.toHaveBeenCalled();
    await vi.advanceTimersByTimeAsync(1);

    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it('renews again before each new token expires', async () => {
    renewForTwoHours();
    start(tokenExpiringIn(3600));

    await vi.advanceTimersByTimeAsync(55 * MINUTE);
    expect(fetchMock).toHaveBeenCalledTimes(1);

    await vi.advanceTimersByTimeAsync(115 * MINUTE - 1);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    await vi.advanceTimersByTimeAsync(1);
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it('reports a failed renewal once and tries again after the minimum delay', async () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => undefined);
    fetchMock.mockImplementation(() => Promise.resolve(jsonResponse({}, 503)));
    start(tokenExpiringIn(60));

    await vi.advanceTimersByTimeAsync(MIN_DELAY);

    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(warn).toHaveBeenCalledTimes(1);
    expect(warn).toHaveBeenCalledWith(
      'Failed to refresh mobile pair token:',
      expect.objectContaining({ message: 'Mobile API failed: 503' }),
    );

    await vi.advanceTimersByTimeAsync(MIN_DELAY - 1);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    await vi.advanceTimersByTimeAsync(1);
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(warn).toHaveBeenCalledTimes(2);
  });

  it('tries again after the minimum delay when the answer carries no token', async () => {
    fetchMock.mockImplementation(() => Promise.resolve(jsonResponse({ data: {} })));
    start(tokenExpiringIn(60));

    await vi.advanceTimersByTimeAsync(MIN_DELAY);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    await vi.advanceTimersByTimeAsync(MIN_DELAY);

    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it('stops before the timer fires', async () => {
    const stop = start(tokenExpiringIn(3600));

    stop();

    expect(vi.getTimerCount()).toBe(0);
    await vi.advanceTimersByTimeAsync(DAY);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('does not schedule the next renewal when it was stopped while one was in flight', async () => {
    const answer = deferred<Response>();
    fetchMock.mockReturnValue(answer.promise);
    const stop = start(tokenExpiringIn(60));
    await vi.advanceTimersByTimeAsync(MIN_DELAY);
    expect(fetchMock).toHaveBeenCalledTimes(1);

    stop();
    const renewed = tokenExpiringIn(3600);
    answer.resolve(jsonResponse({ data: { token: renewed } }));
    await vi.advanceTimersByTimeAsync(0);

    expect(stored()).toBe(renewed);
    expect(vi.getTimerCount()).toBe(0);
    await vi.advanceTimersByTimeAsync(DAY);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it('does not schedule the next renewal when it was stopped while one was failing', async () => {
    vi.spyOn(console, 'warn').mockImplementation(() => undefined);
    const answer = deferred<Response>();
    fetchMock.mockReturnValue(answer.promise);
    const stop = start(tokenExpiringIn(60));
    await vi.advanceTimersByTimeAsync(MIN_DELAY);

    stop();
    answer.reject(new Error('offline'));
    await vi.advanceTimersByTimeAsync(0);

    expect(vi.getTimerCount()).toBe(0);
    await vi.advanceTimersByTimeAsync(DAY);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});
