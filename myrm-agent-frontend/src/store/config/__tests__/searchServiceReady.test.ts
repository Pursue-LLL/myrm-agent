/**
 * What the search-service gate does with an account's search services, through the real config manager, sandbox
 * adapter and config store (only the network is replaced).
 *
 * Cloud start-up returns the first screen's keys and loads the rest in the background, once and without a retry, so
 * the list is empty while that load is in flight and for good once it failed. The gate asks for the key first and
 * waits at most MAX_WAIT_MS for the answer: it decides on the list once the server has answered, and lets the turn
 * through (the server judges it) while the list stays unknown. Local mode fetches every key with the first request,
 * so there is nothing to wait for there.
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

/** The longest the gate stays silent while it waits for the account's search services. */
const MAX_WAIT_MS = 3000;
const FIRST_SCREEN_KEYS = ['providers', 'chatSettings', 'personalSettings'];
const BACKGROUND_LOAD_MS = 40;
const META = { version: '1_0', updatedAt: '2026-01-01T00:00:00.000Z', deviceId: 'device', encrypted: false };
const SEARCH_SERVICE = {
  id: 'svc-1',
  enabled: true,
  priority: 1,
  search_service: 'tavily',
  api_key: 'key',
  createdAt: 1,
};
const SEARCH_ROW = { searchServiceConfigs: [SEARCH_SERVICE] };

interface NetworkScript {
  /** Whether the config service answers at all. */
  configService?: 'answers' | 'silent';
  /** Whether the one request that loads the non-first-screen keys comes back or fails. */
  backgroundLoad: 'lands' | 'fails';
  account: 'has-search-service' | 'has-none';
  /** The request for the `searchServices` key alone: answered (after `singleKeyDelayMs`), failed, or never answered. */
  singleKey?: 'answers' | 'fails' | 'silent';
  singleKeyDelayMs?: number;
}

function respond(status: number, body: unknown): Response {
  return { ok: status < 400, status, statusText: String(status), json: async () => body } as Response;
}

const pause = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

/** A request that never comes back on its own; it ends only when the adapter's own timeout aborts it. */
const silence = (init?: RequestInit) =>
  new Promise<Response>((_resolve, reject) => {
    init?.signal?.addEventListener('abort', () => reject(new DOMException('aborted', 'AbortError')));
  });

function stubNetwork({
  configService = 'answers',
  backgroundLoad,
  account,
  singleKey = 'answers',
  singleKeyDelayMs = 0,
}: NetworkScript) {
  const configured = account === 'has-search-service';
  const row = { key: 'searchServices', value: SEARCH_ROW, ...META };
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    if (configService === 'silent') {
      return silence(init);
    }
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
      await pause(BACKGROUND_LOAD_MS);
      return respond(200, { configs: configured ? { searchServices: row } : {} });
    }
    if (path.endsWith('/config/searchServices')) {
      if (singleKey === 'silent') {
        return silence(init);
      }
      if (singleKey === 'fails') {
        throw new TypeError('network down');
      }
      await pause(singleKeyDelayMs);
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
  const { checkSearchServiceReady } = await import('@/store/config/searchServiceReady');
  const { toast } = await import('@/lib/utils/toast');
  const notice = vi.spyOn(toast, 'warning').mockReturnValue(0);
  return {
    checkSearchServiceReady,
    notice,
    initConfig: () => useConfigStore.getState().initConfig(),
    setSearchServices: (searchServiceConfigs: (typeof SEARCH_SERVICE)[]) =>
      useConfigStore.setState({ searchServiceConfigs }),
    listedServices: () => useConfigStore.getState().searchServiceConfigs.length,
  };
}

type Session = Awaited<ReturnType<typeof startSession>>;

/** A cloud session after start-up whose background load failed, so only the key request can bring the list. */
async function startedSession(script: Omit<NetworkScript, 'backgroundLoad'>): Promise<Session> {
  stubNetwork({ backgroundLoad: 'fails', ...script });
  const session = await startSession();
  await session.initConfig();
  await pause(20);
  return session;
}

/** Starts the gate on the virtual clock and records what it answered. */
function askGate(session: Session) {
  vi.useFakeTimers();
  const answer = vi.fn<(ready: boolean) => void>();
  void session.checkSearchServiceReady().then(answer);
  return answer;
}

describe('checkSearchServiceReady', () => {
  beforeEach(() => {
    deployMode.local = false;
    localStorage.clear();
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it('decides on the list of an account whose background load is still in flight', async () => {
    stubNetwork({ backgroundLoad: 'lands', account: 'has-search-service' });
    const session = await startSession();
    await session.initConfig();
    expect(session.listedServices()).toBe(0);

    await expect(session.checkSearchServiceReady()).resolves.toBe(true);

    expect(session.listedServices()).toBe(1);
    expect(session.notice).not.toHaveBeenCalled();
    await pause(BACKGROUND_LOAD_MS + 20);
  });

  it('decides on the list of an account whose background load failed', async () => {
    const session = await startedSession({ account: 'has-search-service' });
    expect(session.listedServices()).toBe(0);

    await expect(session.checkSearchServiceReady()).resolves.toBe(true);

    expect(session.listedServices()).toBe(1);
    expect(session.notice).not.toHaveBeenCalled();
  });

  it('refuses an account that has no search service, with one setup notice', async () => {
    stubNetwork({ backgroundLoad: 'lands', account: 'has-none' });
    const session = await startSession();
    await session.initConfig();

    await expect(session.checkSearchServiceReady()).resolves.toBe(false);

    expect(session.notice).toHaveBeenCalledTimes(1);
    await pause(BACKGROUND_LOAD_MS + 20);
  });

  it('lets the turn through when the request for the list fails, because the server judges it', async () => {
    const session = await startedSession({ account: 'has-search-service', singleKey: 'fails' });

    await expect(session.checkSearchServiceReady()).resolves.toBe(true);

    expect(session.notice).not.toHaveBeenCalled();
  });

  it('decides on a slow answer that comes back within the limit', async () => {
    const answerAfterMs = MAX_WAIT_MS - 500;
    const session = await startedSession({ account: 'has-none', singleKeyDelayMs: answerAfterMs });
    const answer = askGate(session);

    await vi.advanceTimersByTimeAsync(answerAfterMs);

    expect(answer).toHaveBeenCalledWith(false);
    expect(session.notice).toHaveBeenCalledTimes(1);
  });

  it('stops waiting at the limit and lets the turn through, while the late answer still reaches the store', async () => {
    const session = await startedSession({ account: 'has-search-service', singleKeyDelayMs: MAX_WAIT_MS + 500 });
    const answer = askGate(session);

    await vi.advanceTimersByTimeAsync(MAX_WAIT_MS - 1);
    expect(answer).not.toHaveBeenCalled();

    await vi.advanceTimersByTimeAsync(1);
    expect(answer).toHaveBeenCalledWith(true);
    expect(session.listedServices()).toBe(0);

    await vi.advanceTimersByTimeAsync(500);
    expect(session.listedServices()).toBe(1);
    expect(session.notice).not.toHaveBeenCalled();
  });

  it('lets the turn through at the limit when the key request never comes back', async () => {
    const session = await startedSession({ account: 'has-search-service', singleKey: 'silent' });
    const answer = askGate(session);

    await vi.advanceTimersByTimeAsync(MAX_WAIT_MS - 1);
    expect(answer).not.toHaveBeenCalled();

    await vi.advanceTimersByTimeAsync(1);
    expect(answer).toHaveBeenCalledWith(true);
    expect(session.notice).not.toHaveBeenCalled();
  });

  it('lets the turn through at the limit when the config service has not answered since start-up', async () => {
    stubNetwork({ configService: 'silent', backgroundLoad: 'fails', account: 'has-search-service' });
    const session = await startSession();
    const answer = askGate(session);

    await vi.advanceTimersByTimeAsync(MAX_WAIT_MS - 1);
    expect(answer).not.toHaveBeenCalled();

    await vi.advanceTimersByTimeAsync(1);
    expect(answer).toHaveBeenCalledWith(true);
    expect(session.notice).not.toHaveBeenCalled();
  });

  it('decides on the store at once in local mode, which loads every key with the first request', async () => {
    const fetchMock = stubNetwork({ backgroundLoad: 'lands', account: 'has-search-service' });
    deployMode.local = true;
    const session = await startSession();
    session.setSearchServices([]);

    await expect(session.checkSearchServiceReady()).resolves.toBe(false);
    expect(session.notice).toHaveBeenCalledTimes(1);

    session.setSearchServices([SEARCH_SERVICE]);
    await expect(session.checkSearchServiceReady()).resolves.toBe(true);

    expect(session.notice).toHaveBeenCalledTimes(1);
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
