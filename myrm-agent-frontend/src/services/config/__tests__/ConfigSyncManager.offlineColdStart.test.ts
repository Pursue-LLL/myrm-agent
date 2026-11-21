/**
 * Cold start in cloud mode: only the core keys are loaded before the queued offline changes are replayed. A queued
 * change for any other key is judged against what the server holds for that key, never against an empty cache; a
 * start-up that failed is redone first when the connection returns, so the queue is replayed once.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { getConfigSyncManager, resetConfigSyncManager } from '@/services/config/ConfigSyncManager';
import { saveOfflineQueue } from '@/services/config/offlineQueue';
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
const serverSecurity = { yoloModeEnabled: true, permissions: {}, approvalTimeoutSeconds: 60 };
const queuedSecurity = { ...serverSecurity, yoloModeEnabled: false };

const okResponse = (body: unknown) => ({ ok: true, status: 200, json: () => Promise.resolve(body) }) as Response;
const wireRecord = (key: string, value: unknown, version: string, deviceId: string) => ({
  key,
  value,
  version,
  updatedAt: '2026-01-01T00:00:00.000Z',
  deviceId,
  encrypted: false,
});
/** The user turned YOLO off just before closing the tab; the change was based on `expectedVersion`. */
const queuedChange = (expectedVersion: string): ConfigChange => ({
  key: 'securityConfig',
  value: queuedSecurity as never,
  expectedVersion,
  timestamp: 1,
});

/** Background reads of the non-core keys that have not been answered yet; released after each test. */
const unansweredBatches: Array<() => void> = [];

/**
 * A backend that answers the core keys at once and a single `securityConfig` read with `serverVersion` (written by the
 * web UI), while the background read of the other keys stays unanswered, so only the on-demand read can supply it.
 */
function serveBackend(serverVersion: string, reachable: () => boolean = () => true) {
  const posts: Array<{ changes: ConfigChange[] }> = [];
  global.fetch = vi.fn((url: RequestInfo | URL, init?: RequestInit) => {
    const href = String(url);
    if (!reachable()) {
      return Promise.reject(new TypeError('Failed to fetch'));
    }
    if (init?.method === 'POST') {
      posts.push(JSON.parse(String(init.body)));
      return Promise.resolve(okResponse({ success: true, conflicts: [], newVersions: { securityConfig: '2000_0' } }));
    }
    if (href.endsWith('/config/securityConfig')) {
      return Promise.resolve(okResponse(wireRecord('securityConfig', serverSecurity, serverVersion, 'web')));
    }
    if (CORE_KEYS.every((key) => href.includes(encodeURIComponent(key)))) {
      const configs = Object.fromEntries(CORE_KEYS.map((key) => [key, wireRecord(key, {}, '1000_0', 'dev')]));
      return Promise.resolve(okResponse({ configs }));
    }
    return new Promise<Response>((resolve) => unansweredBatches.push(() => resolve(okResponse({ configs: {} }))));
  }) as unknown as typeof fetch;
  return { posts };
}

describe('ConfigSyncManager cold start with queued offline changes (cloud mode)', () => {
  const resolver = vi.fn();

  beforeEach(() => {
    resetConfigSyncManager();
    vi.restoreAllMocks();
    resolver.mockReset().mockResolvedValue(false);
    localStorage.clear();
  });

  afterEach(() => {
    unansweredBatches.splice(0).forEach((answer) => answer());
    vi.useRealTimers();
    localStorage.clear();
  });

  it('replays a queued change for a non-core key when the server still holds its base version, without asking', async () => {
    const { posts } = serveBackend('1000_5');
    saveOfflineQueue([queuedChange('1000_5')]);
    const manager = getConfigSyncManager();
    manager.setConflictResolver(resolver);

    await manager.initialize();

    expect(resolver).not.toHaveBeenCalled();
    expect(posts).toHaveLength(1);
    expect(posts[0]?.changes).toEqual([expect.objectContaining({ key: 'securityConfig', expectedVersion: '1000_5' })]);
    expect(manager.get('securityConfig')).toEqual(queuedSecurity);
  });

  it('shows the user the server version, writer and value when the server moved on since the change was queued', async () => {
    const { posts } = serveBackend('1000_9');
    saveOfflineQueue([queuedChange('1000_5')]);
    const manager = getConfigSyncManager();
    manager.setConflictResolver(resolver);

    await manager.initialize();

    expect(resolver).toHaveBeenCalledExactlyOnceWith({
      configKey: 'securityConfig',
      localVersion: '1000_5',
      serverVersion: '1000_9',
      deviceId: 'web',
      localValue: queuedSecurity,
      serverValue: serverSecurity,
    });
    expect(posts).toHaveLength(0);
  });

  it('after a failed start-up, loads the server state and replays the queue once when the connection returns', async () => {
    vi.useFakeTimers();
    let reachable = false;
    const { posts } = serveBackend('1000_5', () => reachable);
    const addListener = vi.spyOn(window, 'addEventListener');
    saveOfflineQueue([queuedChange('1000_5')]);
    const manager = getConfigSyncManager();
    manager.setConflictResolver(resolver);

    const starting = manager.initialize();
    await vi.advanceTimersByTimeAsync(1000);
    await starting;
    expect(manager.isInitialized).toBe(false);

    reachable = true;
    const onOnline = addListener.mock.calls.find(([type]) => type === 'online')?.[1] as () => void;
    onOnline();
    await vi.waitFor(() => expect(posts).toHaveLength(1));
    await vi.advanceTimersByTimeAsync(100);

    expect(posts).toHaveLength(1);
    expect(resolver).not.toHaveBeenCalled();
  });
});
