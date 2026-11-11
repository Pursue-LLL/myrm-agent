/**
 * A phone whose browser refuses session storage (privacy settings, in-app browsers) must still be able to use the
 * remote: the pair token then lives in memory for the life of the page.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { kit } from './mobileRemoteKit';

vi.mock('@/lib/e2ee/client', async () => (await import('./mobileRemoteKit')).e2eeClientMock());
vi.mock('@/lib/utils/apiConfig', async () => (await import('./mobileRemoteKit')).apiConfigMock());

const STORAGE_KEY = 'mobile_pair_token';

/** A stand-in for `sessionStorage` whose failures the test controls. */
function stubSessionStorage(initial: Record<string, string> = {}) {
  const control = { data: new Map(Object.entries(initial)), refuseReads: false, refuseWrites: false };
  vi.stubGlobal('sessionStorage', {
    getItem: (key: string) => {
      if (control.refuseReads) {
        throw new DOMException('denied', 'SecurityError');
      }
      return control.data.get(key) ?? null;
    },
    setItem: (key: string, value: string) => {
      if (control.refuseWrites) {
        throw new DOMException('quota', 'QuotaExceededError');
      }
      control.data.set(key, value);
    },
  });
  return control;
}

const address = () => window.location.pathname + window.location.search + window.location.hash;
const goTo = (url: string) => window.history.replaceState(null, '', url);

/** A fresh module each time: a token the page holds in memory lasts as long as the module does. */
async function loadMobileRemote() {
  vi.resetModules();
  return import('../mobileRemote');
}

beforeEach(() => {
  vi.resetAllMocks();
  goTo('/mobile');
  kit.loadStoredE2EESession.mockReturnValue(null);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('pair token when session storage refuses it', () => {
  it('takes the token from the address, removes it from the address and keeps it for the page', async () => {
    const control = stubSessionStorage();
    control.refuseWrites = true;
    goTo('/mobile/status/c1?view=live&pair=tok#top');
    const { getMobilePairToken } = await loadMobileRemote();

    expect(getMobilePairToken()).toBe('tok');

    expect(address()).toBe('/mobile/status/c1?view=live#top');
    expect(getMobilePairToken()).toBe('tok');
    expect(control.data.size).toBe(0);
  });

  it('keeps a renewed token for the page, the newest one winning', async () => {
    stubSessionStorage().refuseWrites = true;
    const { getMobilePairToken, storeMobilePairToken } = await loadMobileRemote();

    storeMobilePairToken('first');
    expect(getMobilePairToken()).toBe('first');

    storeMobilePairToken('second');
    expect(getMobilePairToken()).toBe('second');
  });

  it('prefers the token the page holds over an older one storage still has', async () => {
    const control = stubSessionStorage({ [STORAGE_KEY]: 'old' });
    const { getMobilePairToken, storeMobilePairToken } = await loadMobileRemote();
    control.refuseWrites = true;

    storeMobilePairToken('new');

    expect(getMobilePairToken()).toBe('new');
    expect(control.data.get(STORAGE_KEY)).toBe('old');
  });

  it('hands authority back to storage once a write is accepted again', async () => {
    const control = stubSessionStorage();
    const { getMobilePairToken, storeMobilePairToken } = await loadMobileRemote();
    control.refuseWrites = true;
    storeMobilePairToken('held');

    control.refuseWrites = false;
    storeMobilePairToken('saved');
    expect(control.data.get(STORAGE_KEY)).toBe('saved');
    expect(getMobilePairToken()).toBe('saved');

    control.data.set(STORAGE_KEY, 'changed elsewhere');
    expect(getMobilePairToken()).toBe('changed elsewhere');
  });

  it('has no token when storage cannot be read and none was kept', async () => {
    stubSessionStorage().refuseReads = true;
    const { getMobilePairToken } = await loadMobileRemote();

    expect(getMobilePairToken()).toBeUndefined();
  });

  it('sends the held token with remote requests', async () => {
    stubSessionStorage().refuseWrites = true;
    goTo('/mobile?pair=tok');
    const { getMobilePairToken, withMobilePairHeaders } = await loadMobileRemote();
    getMobilePairToken();

    expect(withMobilePairHeaders({ Accept: 'application/json' })).toEqual({
      Accept: 'application/json',
      'X-Pair-Token': 'tok',
    });
  });
});
