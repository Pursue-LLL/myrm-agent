/**
 * Lifecycle of the sync layer's write path: the debounce timer and the online listener belong to one manager and are
 * released when it is disposed or when the singleton is reset.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ConfigSyncManager, getConfigSyncManager, resetConfigSyncManager } from '@/services/config/ConfigSyncManager';
import { DEFAULT_PERSONAL_SETTINGS } from '@/services/config/types';

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

const okResponse = (body: unknown) => ({ ok: true, status: 200, json: () => Promise.resolve(body) }) as Response;

/** A backend that holds no configuration and accepts every write; `posts` lists the writes it received. */
function serveEmptyBackend() {
  const posts: unknown[] = [];
  global.fetch = vi.fn((_url: RequestInfo | URL, init?: RequestInit) => {
    if (init?.method === 'POST') {
      posts.push(JSON.parse(String(init.body)));
      return Promise.resolve(okResponse({ success: true, conflicts: [], newVersions: { personalSettings: '1000_1' } }));
    }
    return Promise.resolve(okResponse({ configs: {} }));
  }) as unknown as typeof fetch;
  return { posts };
}

const editedSettings = { ...DEFAULT_PERSONAL_SETTINGS, systemInstructions: 'edited' };

describe('config outbox lifecycle', () => {
  beforeEach(() => {
    resetConfigSyncManager();
    vi.restoreAllMocks();
    localStorage.clear();
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
    localStorage.clear();
  });

  it('dispose drops the debounced write that has not been sent yet', async () => {
    const { posts } = serveEmptyBackend();
    const manager = new ConfigSyncManager();
    await manager.initialize();
    manager.set('personalSettings', editedSettings);

    manager.dispose();
    await vi.advanceTimersByTimeAsync(5000);

    expect(posts).toHaveLength(0);
  });

  it('resetConfigSyncManager releases the timers of the singleton it discards', async () => {
    const { posts } = serveEmptyBackend();
    const manager = getConfigSyncManager();
    await manager.initialize();
    manager.set('personalSettings', editedSettings);

    resetConfigSyncManager();
    await vi.advanceTimersByTimeAsync(5000);

    expect(posts).toHaveLength(0);
  });

  it('dispose removes the online listener that a failed start-up registered', async () => {
    const addListener = vi.spyOn(window, 'addEventListener');
    const removeListener = vi.spyOn(window, 'removeEventListener');
    global.fetch = vi.fn(() => Promise.reject(new TypeError('Failed to fetch'))) as unknown as typeof fetch;
    const manager = new ConfigSyncManager();

    const starting = manager.initialize();
    await vi.advanceTimersByTimeAsync(2000);
    await starting;
    const onOnline = addListener.mock.calls.find(([type]) => type === 'online')?.[1];
    expect(onOnline).toBeDefined();

    manager.dispose();

    expect(removeListener).toHaveBeenCalledWith('online', onOnline);
  });
});
