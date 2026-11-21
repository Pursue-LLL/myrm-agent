/**
 * A change the backend did not take is kept and tried again after pauses that double up to a minute; the backend
 * answering starts the pauses over. A background send that the backend refuses is logged, never an unhandled rejection.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { getConfigSyncManager, resetConfigSyncManager } from '@/services/config/ConfigSyncManager';
import type { ConfigChange } from '@/services/config/types';

vi.mock('@/lib/deploy-mode', () => ({
  isLocalMode: () => false,
  getApiBaseUrl: () => 'http://test.local',
}));
vi.mock('@/lib/backend-health', () => ({
  ensureLocalBackendReady: vi.fn(),
}));
vi.mock('@/lib/platform-readiness', () => ({
  ensurePlatformReadiness: vi.fn(),
}));
vi.mock('@/lib/guest', () => ({
  getAuthToken: () => 'test-token',
}));

const CORE_KEYS = ['providers', 'chatSettings', 'personalSettings'];
const OFFLINE_QUEUE_KEY = 'config-offline-queue';

type Backend = 'up' | 'unavailable' | 'refusing';

const response = (status: number, body: unknown = {}) =>
  ({ ok: status >= 200 && status < 300, status, json: () => Promise.resolve(body) }) as Response;
const wireRecord = (key: string) => ({
  key,
  value: {},
  version: '1000_0',
  updatedAt: '2026-01-01T00:00:00.000Z',
  deviceId: 'dev',
  encrypted: false,
});

/** A backend that serves the core keys and takes writes while `state.backend` is up; every write is recorded. */
function serve(state: { backend: Backend }) {
  const posts: Array<{ at: number; changes: ConfigChange[] }> = [];
  global.fetch = vi.fn((_url: RequestInfo | URL, init?: RequestInit) => {
    if (init?.method !== 'POST') {
      return Promise.resolve(
        response(200, { configs: Object.fromEntries(CORE_KEYS.map((key) => [key, wireRecord(key)])) }),
      );
    }
    const { changes } = JSON.parse(String(init.body)) as { changes: ConfigChange[] };
    posts.push({ at: Date.now(), changes });
    if (state.backend === 'unavailable') {
      return Promise.resolve(response(503));
    }
    if (state.backend === 'refusing') {
      return Promise.resolve(response(422, { detail: 'invalid' }));
    }
    const newVersions = Object.fromEntries(changes.map((change) => [change.key, '2000_0']));
    return Promise.resolve(response(200, { success: true, conflicts: [], newVersions }));
  }) as unknown as typeof fetch;
  return posts;
}

const storedKeys = () =>
  (JSON.parse(localStorage.getItem(OFFLINE_QUEUE_KEY) ?? '[]') as ConfigChange[]).map((c) => c.key);

describe('config outbox retention (cloud mode)', () => {
  const state = { backend: 'up' as Backend };

  beforeEach(() => {
    vi.useFakeTimers();
    vi.spyOn(console, 'warn').mockImplementation(() => {});
    resetConfigSyncManager();
    localStorage.clear();
    state.backend = 'up';
  });

  afterEach(() => {
    resetConfigSyncManager();
    vi.clearAllTimers();
    vi.useRealTimers();
    vi.restoreAllMocks();
    localStorage.clear();
  });

  it('keeps the change and says so while the backend is unavailable', async () => {
    state.backend = 'unavailable';
    serve(state);
    const manager = getConfigSyncManager();
    await manager.initialize();

    manager.set('chatSettings', { a: 1 } as never);
    const result = await manager.forceSync();

    expect(result).toMatchObject({ success: false, error: 'Backend not available' });
    expect(storedKeys()).toEqual(['chatSettings']);
    expect(manager.status).toBe('offline');
  });

  it('retries after pauses that double up to a minute, and starts over once the backend has answered', async () => {
    state.backend = 'unavailable';
    const posts = serve(state);
    const manager = getConfigSyncManager();
    await manager.initialize();
    manager.set('chatSettings', { a: 1 } as never);
    await manager.forceSync();

    const pauses = [1000, 2000, 4000, 8000, 16000, 32000, 60000, 60000];
    for (const [attempt, pause] of pauses.entries()) {
      await vi.advanceTimersByTimeAsync(pause - 1);
      expect(posts).toHaveLength(attempt + 1);
      await vi.advanceTimersByTimeAsync(1);
      expect(posts).toHaveLength(attempt + 2);
    }

    state.backend = 'up';
    await vi.advanceTimersByTimeAsync(60000);
    expect(manager.status).toBe('idle');
    expect(storedKeys()).toEqual([]);

    state.backend = 'unavailable';
    manager.set('chatSettings', { a: 2 } as never);
    await manager.forceSync();
    const attempts = posts.length;
    await vi.advanceTimersByTimeAsync(999);
    expect(posts).toHaveLength(attempts);
    await vi.advanceTimersByTimeAsync(1);
    expect(posts).toHaveLength(attempts + 1);
  });

  it('keeps a single retry waiting, however many sends fail meanwhile', async () => {
    state.backend = 'unavailable';
    const posts = serve(state);
    const manager = getConfigSyncManager();
    await manager.initialize();
    manager.set('chatSettings', { a: 1 } as never);
    await manager.forceSync();

    await vi.advanceTimersByTimeAsync(500);
    manager.set('chatSettings', { a: 2 } as never);
    await vi.advanceTimersByTimeAsync(5500);

    // The retry at 1 s, the debounced send of the second edit at 1.5 s, the retry the second failure armed at 3 s.
    expect(posts.map((post) => post.at - (posts[0]?.at ?? 0))).toEqual([0, 1000, 1500, 3000]);
  });

  it('delivers the kept change, on the version it was based on, once the backend is back', async () => {
    state.backend = 'unavailable';
    const posts = serve(state);
    const manager = getConfigSyncManager();
    await manager.initialize();
    manager.set('chatSettings', { a: 1 } as never);
    await manager.forceSync();

    state.backend = 'up';
    await vi.advanceTimersByTimeAsync(1000);

    expect(posts.at(-1)?.changes).toEqual([
      expect.objectContaining({ key: 'chatSettings', value: { a: 1 }, expectedVersion: '1000_0' }),
    ]);
    expect(manager.getRecord('chatSettings')?.meta.version).toBe('2000_0');
    expect(storedKeys()).toEqual([]);
  });

  it('logs a refused background write instead of leaving an unhandled rejection', async () => {
    vi.useRealTimers();
    state.backend = 'refusing';
    serve(state);
    const manager = getConfigSyncManager();
    await manager.initialize();
    const unhandled: unknown[] = [];
    const onUnhandled = (reason: unknown) => unhandled.push(reason);
    process.on('unhandledRejection', onUnhandled);

    manager.set('securityConfig', { yoloModeEnabled: false } as never);
    await new Promise((resolve) => setTimeout(resolve, 50));
    process.off('unhandledRejection', onUnhandled);

    expect(unhandled).toEqual([]);
    expect(manager.status).toBe('error');
  });
});
