/**
 * Regression cover for the offline-queue replay that used to overwrite newer server config.
 *
 * A queued change records the server version it was based on (`expectedVersion`). If the server moved on
 * since then, replaying the queued snapshot silently replaced the server's newer configuration (providers
 * and the default model disappeared). The replay must detect that staleness and keep the server value.
 */

import { describe, expect, it, beforeEach, afterEach, vi } from 'vitest';
import { ConfigSyncManager, resetConfigSyncManager } from '@/services/config/ConfigSyncManager';
import { DEFAULT_PERSONAL_SETTINGS, type PersonalSettingsConfigValue } from '@/services/config/types';

vi.mock('@/lib/deploy-mode', () => ({
  isLocalMode: vi.fn(() => true),
  getApiBaseUrl: vi.fn(() => 'http://localhost:8080/api/v1'),
}));

vi.mock('@/lib/backend-health', () => ({
  ensureLocalBackendReady: vi.fn(() => Promise.resolve(true)),
  markLocalBackendUnreachable: vi.fn(),
}));

vi.mock('@/lib/platform-readiness', () => ({
  ensurePlatformReadiness: vi.fn(() => Promise.resolve({ state: 'ready', database: true })),
  whenDatabaseReady: vi.fn(() => Promise.resolve(true)),
}));

const mockFetch = vi.fn();
global.fetch = mockFetch;

const OFFLINE_QUEUE_KEY = 'config-offline-queue';

const localStorageMock = (() => {
  let store: Record<string, string> = {};
  return {
    getItem: vi.fn((key: string) => store[key] || null),
    setItem: vi.fn((key: string, value: string) => {
      store[key] = value;
    }),
    removeItem: vi.fn((key: string) => {
      delete store[key];
    }),
    clear: vi.fn(() => {
      store = {};
    }),
  };
})();
Object.defineProperty(global, 'localStorage', { value: localStorageMock });

describe('ConfigSyncManager offline replay staleness guard', () => {
  let manager: ConfigSyncManager;

  const createSettings = (overrides?: Partial<PersonalSettingsConfigValue>): PersonalSettingsConfigValue => ({
    ...DEFAULT_PERSONAL_SETTINGS,
    ...overrides,
  });

  const serverConfigs = (value: PersonalSettingsConfigValue, version: string) => ({
    configs: {
      personalSettings: {
        key: 'personalSettings',
        value,
        version,
        updatedAt: '2026-01-01T00:00:00.000Z',
        deviceId: 'tauri-local',
      },
    },
  });

  beforeEach(() => {
    vi.clearAllMocks();
    localStorageMock.clear();
    resetConfigSyncManager();
    manager = new ConfigSyncManager();
  });

  afterEach(() => {
    resetConfigSyncManager();
  });

  it('keeps the newer server value when the queued change is based on an older version', async () => {
    const serverValue = createSettings({ activeThemeProfileId: 'ocean-blue' });
    const queuedValue = createSettings({ activeThemeProfileId: 'forest-green' });

    localStorageMock.setItem(
      OFFLINE_QUEUE_KEY,
      JSON.stringify([
        {
          key: 'personalSettings',
          value: queuedValue,
          expectedVersion: '1000_0',
          timestamp: Date.now(),
        },
      ]),
    );

    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve(serverConfigs(serverValue, '1000_7')),
    });

    await manager.initialize();

    // 服务器已经前进到 1000_7：队列里的 1000_0 快照过期，不能覆盖服务端。
    expect(manager.get('personalSettings')?.activeThemeProfileId).toBe('ocean-blue');
    // 过期队列必须被清掉，否则每次启动都会重放一次。
    expect(localStorageMock.getItem(OFFLINE_QUEUE_KEY)).toBeNull();
    // 不应发生第二次请求（没有可重放的变更）。
    expect(mockFetch).toHaveBeenCalledTimes(1);
  });

  it('asks the conflict resolver before discarding a stale queued change', async () => {
    const serverValue = createSettings({ activeThemeProfileId: 'ocean-blue' });
    const queuedValue = createSettings({ activeThemeProfileId: 'forest-green' });

    localStorageMock.setItem(
      OFFLINE_QUEUE_KEY,
      JSON.stringify([
        {
          key: 'personalSettings',
          value: queuedValue,
          expectedVersion: '1000_0',
          timestamp: Date.now(),
        },
      ]),
    );

    const resolver = vi.fn().mockResolvedValue(true);
    manager.setConflictResolver(resolver);

    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve(serverConfigs(serverValue, '1000_7')),
    });
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () =>
        Promise.resolve({
          success: true,
          conflicts: [],
          newVersions: { personalSettings: '1000_8' },
        }),
    });

    await manager.initialize();

    expect(resolver).toHaveBeenCalledTimes(1);
    expect(resolver.mock.calls[0][0]).toMatchObject({
      configKey: 'personalSettings',
      localVersion: '1000_0',
      serverVersion: '1000_7',
    });
    // 用户选择保留本地值 → 变更被重放。
    expect(manager.get('personalSettings')?.activeThemeProfileId).toBe('forest-green');
  });

  it('still replays a queued change when the server has not moved since', async () => {
    const serverValue = createSettings({ activeThemeProfileId: 'official-default' });
    const queuedValue = createSettings({ activeThemeProfileId: 'ocean-blue' });

    localStorageMock.setItem(
      OFFLINE_QUEUE_KEY,
      JSON.stringify([
        {
          key: 'personalSettings',
          value: queuedValue,
          expectedVersion: '1000_0',
          timestamp: Date.now(),
        },
      ]),
    );

    mockFetch
      .mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve(serverConfigs(serverValue, '1000_0')),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: () =>
          Promise.resolve({
            success: true,
            conflicts: [],
            newVersions: { personalSettings: '1000_1' },
          }),
      });

    await manager.initialize();

    expect(manager.get('personalSettings')?.activeThemeProfileId).toBe('ocean-blue');
    expect(localStorageMock.getItem(OFFLINE_QUEUE_KEY)).toBeNull();
  });

  it('sends the queued base version so the server optimistic lock can reject a stale write', async () => {
    const serverValue = createSettings({ activeThemeProfileId: 'official-default' });
    const queuedValue = createSettings({ activeThemeProfileId: 'ocean-blue' });

    localStorageMock.setItem(
      OFFLINE_QUEUE_KEY,
      JSON.stringify([
        {
          key: 'personalSettings',
          value: queuedValue,
          expectedVersion: '1000_0',
          timestamp: Date.now(),
        },
      ]),
    );

    mockFetch
      .mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve(serverConfigs(serverValue, '1000_0')),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: () =>
          Promise.resolve({
            success: true,
            conflicts: [],
            newVersions: { personalSettings: '1000_1' },
          }),
      });

    await manager.initialize();

    const syncCall = mockFetch.mock.calls.find((call) => {
      const url = String(call[0]);
      return url.includes('/config/sync');
    });
    expect(syncCall).toBeDefined();
    const body = JSON.parse(String(syncCall?.[1]?.body)) as {
      changes: Array<{ key: string; expectedVersion?: string }>;
    };
    expect(body.changes[0].expectedVersion).toBe('1000_0');
  });
});
