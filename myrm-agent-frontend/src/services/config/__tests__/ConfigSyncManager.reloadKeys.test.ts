/**
 * What the manager does when the backend changes a config row while the page is open (the migration wizard writes
 * model slots, MCP servers and global instructions): `reloadKeys` makes the cache, the subscribers and the version of
 * the next write follow the backend, so the next edit neither shows old values nor collides with the backend's write.
 */

import { afterEach, beforeEach, describe, expect, it, vi, type Mock } from 'vitest';
import {
  getConfigSyncManager,
  resetConfigSyncManager,
  type ConfigConflictResolver,
} from '@/services/config/ConfigSyncManager';
import type { ConfigChangeListener } from '@/services/config/configListeners';
import type { ConfigKey, SyncResult } from '@/services/config/types';

const KEY: ConfigKey = 'providers';
const DEVICE = 'dev-local';

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

type Providers = { providers: { id: string; isEnabled: boolean; apiKeys: string[] }[] };

const withKeys = (apiKeys: string[], isEnabled = true): Providers => ({
  providers: [{ id: 'openai', isEnabled, apiKeys }],
});
const record = (value: Providers, version: string, deviceId: string) => ({
  key: KEY,
  value: value as never,
  meta: { version, updatedAt: '2026-01-01T00:00:00.000Z', deviceId },
});

const accepted: SyncResult = { success: true, conflicts: [], newVersions: new Map([[KEY, '1000_6']]) };

describe('ConfigSyncManager.reloadKeys', () => {
  const synced = withKeys([]);
  const imported = withKeys(['imported-key']);
  let manager: ReturnType<typeof getConfigSyncManager>;
  let sync: ReturnType<typeof vi.fn>;
  let getAll: ReturnType<typeof vi.fn>;
  let listener: ReturnType<typeof vi.fn<ConfigChangeListener<typeof KEY>>>;
  let resolver: Mock<ConfigConflictResolver>;

  /** The page holds `synced` at version 1000_0; the backend's copy is whatever `getAll` is told to return. */
  beforeEach(() => {
    vi.useFakeTimers();
    localStorageMock.clear();
    resetConfigSyncManager();
    manager = getConfigSyncManager();
    sync = vi.fn().mockResolvedValue(accepted);
    getAll = vi.fn();
    listener = vi.fn<ConfigChangeListener<typeof KEY>>();
    resolver = vi.fn<ConfigConflictResolver>(() => true);
    Object.assign(manager, {
      adapter: { getDeviceId: () => DEVICE, sync, getAll },
      cache: new Map([[KEY, record(synced, '1000_0', DEVICE)]]),
      baseCache: new Map([[KEY, record(synced, '1000_0', DEVICE)]]),
      _isInitialized: true,
    });
    manager.subscribe(KEY, listener);
    manager.setConflictResolver(resolver);
  });

  afterEach(() => {
    vi.clearAllTimers();
    vi.useRealTimers();
    resetConfigSyncManager();
  });

  it('shows what another writer stored and sends the next edit on the version it stored', async () => {
    getAll.mockResolvedValue(new Map([[KEY, record(imported, '1000_5', 'competitor-migration')]]));

    await manager.reloadKeys([KEY]);

    expect(getAll).toHaveBeenCalledExactlyOnceWith([KEY]);
    expect(manager.get(KEY)).toEqual(imported);
    expect(listener).toHaveBeenCalledExactlyOnceWith(KEY, imported, expect.objectContaining({ version: '1000_5' }));

    const edited = withKeys(['imported-key'], false);
    manager.set(KEY, edited as never);
    await manager.forceSync();

    expect(sync).toHaveBeenCalledOnce();
    expect(sync).toHaveBeenCalledWith([
      expect.objectContaining({ key: KEY, value: edited, expectedVersion: '1000_5' }),
    ]);
    expect(resolver).not.toHaveBeenCalled();
  });

  it('keeps an edit that has not reached the backend yet', async () => {
    const edited = withKeys([], false);
    manager.set(KEY, edited as never);
    getAll.mockResolvedValue(new Map([[KEY, record(imported, '1000_5', 'competitor-migration')]]));

    await manager.reloadKeys([KEY]);

    expect(manager.get(KEY)).toEqual(edited);
    expect(listener).toHaveBeenCalledTimes(1);
  });

  it('fails without touching the cache when the backend cannot be read', async () => {
    getAll.mockRejectedValue(new Error('backend unreachable'));

    await expect(manager.reloadKeys([KEY])).rejects.toThrow('backend unreachable');

    expect(manager.get(KEY)).toEqual(synced);
    expect(listener).not.toHaveBeenCalled();
  });
});
