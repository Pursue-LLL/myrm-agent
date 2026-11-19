/**
 * What `ensureSearchServicesLoaded` gives a gate that decides on the search services, through the real config
 * manager, sandbox adapter and config store (only the network is replaced).
 *
 * Cloud start-up returns the first screen's keys and loads the rest in the background, once and without a retry; the
 * gate therefore sees an empty list while that load is in flight, and for good once it failed. Local mode fetches
 * every key with the first request, so there is nothing to wait for there.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const deployMode = vi.hoisted(() => ({ local: false }));

vi.mock('@/lib/deploy-mode', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/deploy-mode')>();
  return { ...actual, isLocalMode: () => deployMode.local, getApiBaseUrl: () => 'http://config.test' };
});
vi.mock('@/lib/guest', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/guest')>();
  return { ...actual, getAuthToken: () => 'test-token' };
});

const FIRST_SCREEN_KEYS = ['providers', 'chatSettings', 'personalSettings'];
const BACKGROUND_LOAD_MS = 40;
const META = { version: '1_0', updatedAt: '2026-01-01T00:00:00.000Z', deviceId: 'device', encrypted: false };
const SEARCH_ROW = {
  searchServiceConfigs: [
    { id: 'svc-1', enabled: true, priority: 1, search_service: 'tavily', api_key: 'key', createdAt: 1 },
  ],
};

interface NetworkScript {
  /** Whether the one request that loads the non-first-screen keys comes back or fails. */
  backgroundLoad: 'lands' | 'fails';
  account: 'has-search-service' | 'has-none';
}

function respond(status: number, body: unknown): Response {
  return { ok: status < 400, status, statusText: String(status), json: async () => body } as Response;
}

function stubNetwork({ backgroundLoad, account }: NetworkScript) {
  const configured = account === 'has-search-service';
  const row = { key: 'searchServices', value: SEARCH_ROW, ...META };
  const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const path = String(input);
    if (path.includes('/config?keys=')) {
      if (FIRST_SCREEN_KEYS.every((key) => path.includes(encodeURIComponent(key)))) {
        return respond(200, {
          configs: Object.fromEntries(FIRST_SCREEN_KEYS.map((key) => [key, { key, value: {}, ...META }])),
        });
      }
      if (backgroundLoad === 'fails') {
        throw new TypeError('network down');
      }
      await new Promise((resolve) => setTimeout(resolve, BACKGROUND_LOAD_MS));
      return respond(200, { configs: configured ? { searchServices: row } : {} });
    }
    if (path.endsWith('/config/searchServices')) {
      return configured ? respond(200, row) : respond(404, {});
    }
    throw new Error(`unexpected request: ${path}`);
  });
  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
}

async function startSession() {
  vi.resetModules();
  const { default: useConfigStore } = await import('@/store/useConfigStore');
  const { ensureSearchServicesLoaded, getActiveSearchServiceConfig } = await import('@/store/config/searchService');
  await useConfigStore.getState().initConfig();
  return {
    ensureSearchServicesLoaded,
    hasUsableSearchService: () => getActiveSearchServiceConfig(useConfigStore.getState().searchServiceConfigs) !== null,
  };
}

const settle = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

describe('ensureSearchServicesLoaded', () => {
  beforeEach(() => {
    deployMode.local = false;
    localStorage.clear();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('hands over the list of an account while the background load is still in flight', async () => {
    stubNetwork({ backgroundLoad: 'lands', account: 'has-search-service' });
    const session = await startSession();
    expect(session.hasUsableSearchService()).toBe(false);

    await session.ensureSearchServicesLoaded();

    expect(session.hasUsableSearchService()).toBe(true);
    await settle(BACKGROUND_LOAD_MS + 20);
  });

  it('hands over the list of an account whose background load failed', async () => {
    stubNetwork({ backgroundLoad: 'fails', account: 'has-search-service' });
    const session = await startSession();
    await settle(20);
    expect(session.hasUsableSearchService()).toBe(false);

    await session.ensureSearchServicesLoaded();

    expect(session.hasUsableSearchService()).toBe(true);
  });

  it('leaves an account without a search service unconfigured', async () => {
    stubNetwork({ backgroundLoad: 'lands', account: 'has-none' });
    const session = await startSession();

    await expect(session.ensureSearchServicesLoaded()).resolves.toBeUndefined();

    expect(session.hasUsableSearchService()).toBe(false);
    await settle(BACKGROUND_LOAD_MS + 20);
  });

  it('does not wait in local mode, which loads every key with the first request', async () => {
    const fetchMock = stubNetwork({ backgroundLoad: 'lands', account: 'has-search-service' });
    deployMode.local = true;
    vi.resetModules();
    const { ensureSearchServicesLoaded } = await import('@/store/config/searchService');

    const outcome = await Promise.race([
      ensureSearchServicesLoaded().then(() => 'returned'),
      settle(200).then(() => 'still waiting'),
    ]);

    expect(outcome).toBe('returned');
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
