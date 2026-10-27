/**
 * What the manager does with a key the backend rejected on version: merge silently when the edits do not overlap,
 * keep the local value on the same device, ask the user across devices, and never lose the local value when the
 * re-send fails.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ConfigSyncManager, getConfigSyncManager, resetConfigSyncManager } from '@/services/config/ConfigSyncManager';
import type { ConfigChangeListener } from '@/services/config/configListeners';
import type { ConfigKey, SyncResult } from '@/services/config/types';

const KEY: ConfigKey = 'chatSettings';
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

type Doc = Record<string, number>;

const meta = (version: string, deviceId: string) => ({ version, updatedAt: '2026-01-01T00:00:00.000Z', deviceId });
const record = (key: ConfigKey, value: Doc, version: string, deviceId: string) => ({
  key,
  value: value as never,
  meta: meta(version, deviceId),
});

const conflictOn = (...keys: ConfigKey[]): SyncResult => ({ success: false, conflicts: keys, newVersions: new Map() });
const accepted = (version: string): SyncResult => ({
  success: true,
  conflicts: [],
  newVersions: new Map([[KEY, version]]),
});

const syncedChanges = (sync: ReturnType<typeof vi.fn>, call: number) =>
  sync.mock.calls[call]?.[0] as { key: string; value: Doc; expectedVersion: string }[];

describe('ConfigSyncManager version conflicts', () => {
  const deviceId = 'dev-local';
  let manager: ConfigSyncManager;
  let sync: ReturnType<typeof vi.fn>;
  let get: ReturnType<typeof vi.fn>;
  let listener: ReturnType<typeof vi.fn<ConfigChangeListener<typeof KEY>>>;

  /** A manager that already holds `base` as the confirmed server value of KEY, then edits it locally to `local`. */
  const editLocally = (base: Doc, local: Doc) => {
    Object.assign(manager, {
      adapter: { getDeviceId: () => deviceId, sync, get },
      cache: new Map([[KEY, record(KEY, base, '1000_0', deviceId)]]),
      baseCache: new Map([[KEY, record(KEY, base, '1000_0', deviceId)]]),
      _isInitialized: true,
    });
    manager.subscribe(KEY, listener);
    manager.set(KEY, local as never);
  };

  const serverHolds = (value: Doc, writtenBy: string) => get.mockResolvedValue(record(KEY, value, '1000_5', writtenBy));

  beforeEach(() => {
    vi.useFakeTimers();
    localStorageMock.clear();
    resetConfigSyncManager();
    manager = getConfigSyncManager();
    sync = vi.fn();
    get = vi.fn();
    listener = vi.fn<ConfigChangeListener<typeof KEY>>();
  });

  afterEach(() => {
    vi.clearAllTimers();
    vi.useRealTimers();
    resetConfigSyncManager();
  });

  it('merges edits that touch different fields without asking anyone, and re-sends the merge on the server version', async () => {
    editLocally({ a: 1, b: 1 }, { a: 2, b: 1 });
    serverHolds({ a: 1, b: 3 }, 'dev-remote');
    sync.mockResolvedValueOnce(conflictOn(KEY)).mockResolvedValueOnce(accepted('1000_9'));
    const resolver = vi.fn();
    manager.setConflictResolver(resolver);

    await manager.forceSync();

    expect(resolver).not.toHaveBeenCalled();
    expect(syncedChanges(sync, 1)).toEqual([
      expect.objectContaining({ key: KEY, value: { a: 2, b: 3 }, expectedVersion: '1000_5' }),
    ]);
    expect(manager.get(KEY)).toEqual({ a: 2, b: 3 });
    expect(manager.getRecord(KEY)?.meta.version).toBe('1000_9');
    expect(listener).toHaveBeenLastCalledWith(KEY, { a: 2, b: 3 }, expect.anything());
  });

  it('keeps the local value without asking when the same device wrote the clashing server version', async () => {
    editLocally({ a: 1 }, { a: 2 });
    serverHolds({ a: 3 }, deviceId);
    sync.mockResolvedValueOnce(conflictOn(KEY)).mockResolvedValueOnce(accepted('1000_9'));
    const resolver = vi.fn();
    manager.setConflictResolver(resolver);

    await manager.forceSync();

    expect(resolver).not.toHaveBeenCalled();
    expect(syncedChanges(sync, 1)).toEqual([expect.objectContaining({ value: { a: 2 }, expectedVersion: '1000_5' })]);
    expect(manager.get(KEY)).toEqual({ a: 2 });
  });

  it('keeps the local value when another device clashed and no resolver is registered', async () => {
    editLocally({ a: 1 }, { a: 2 });
    serverHolds({ a: 3 }, 'dev-remote');
    sync.mockResolvedValueOnce(conflictOn(KEY)).mockResolvedValueOnce(accepted('1000_9'));

    await manager.forceSync();

    expect(syncedChanges(sync, 1)).toEqual([expect.objectContaining({ value: { a: 2 }, expectedVersion: '1000_5' })]);
  });

  it('shows the resolver both values and re-sends the local one when it says keep local', async () => {
    editLocally({ a: 1 }, { a: 2 });
    serverHolds({ a: 3 }, 'dev-remote');
    sync.mockResolvedValueOnce(conflictOn(KEY)).mockResolvedValueOnce(accepted('1000_9'));
    const resolver = vi.fn().mockResolvedValue(true);
    manager.setConflictResolver(resolver);

    await manager.forceSync();

    expect(resolver).toHaveBeenCalledWith({
      configKey: KEY,
      localVersion: expect.any(String),
      serverVersion: '1000_5',
      deviceId: 'dev-remote',
      localValue: { a: 2 },
      serverValue: { a: 3 },
    });
    expect(syncedChanges(sync, 1)).toEqual([expect.objectContaining({ value: { a: 2 } })]);
  });

  it('adopts the server value, tells subscribers, and sends nothing more when the resolver says use the server', async () => {
    editLocally({ a: 1 }, { a: 2 });
    serverHolds({ a: 3 }, 'dev-remote');
    sync.mockResolvedValueOnce(conflictOn(KEY));
    manager.setConflictResolver(vi.fn().mockResolvedValue(false));

    await manager.forceSync();

    expect(sync).toHaveBeenCalledTimes(1);
    expect(manager.get(KEY)).toEqual({ a: 3 });
    expect(manager.getRecord(KEY)?.meta.version).toBe('1000_5');
    expect(listener).toHaveBeenLastCalledWith(KEY, { a: 3 }, expect.objectContaining({ version: '1000_5' }));
  });

  it('keeps the local value when the resolver itself fails', async () => {
    editLocally({ a: 1 }, { a: 2 });
    serverHolds({ a: 3 }, 'dev-remote');
    sync.mockResolvedValueOnce(conflictOn(KEY)).mockResolvedValueOnce(accepted('1000_9'));
    manager.setConflictResolver(vi.fn().mockRejectedValue(new Error('dialog closed')));
    vi.spyOn(console, 'warn').mockImplementation(() => {});

    await manager.forceSync();

    expect(manager.get(KEY)).toEqual({ a: 2 });
    expect(syncedChanges(sync, 1)).toEqual([expect.objectContaining({ value: { a: 2 } })]);
  });

  it('queues the re-send for a later retry, and persists it, when the backend rejects it again', async () => {
    editLocally({ a: 1 }, { a: 2 });
    serverHolds({ a: 3 }, deviceId);
    sync
      .mockResolvedValueOnce(conflictOn(KEY))
      .mockResolvedValueOnce({ success: false, conflicts: [], newVersions: new Map(), error: 'Backend not available' });
    vi.spyOn(console, 'warn').mockImplementation(() => {});

    await manager.forceSync();

    const queued = JSON.parse(String(localStorageMock.getItem(OFFLINE_QUEUE_KEY))) as {
      key: string;
      value: Doc;
      expectedVersion: string;
    }[];
    expect(queued).toEqual([expect.objectContaining({ key: KEY, value: { a: 2 }, expectedVersion: '1000_5' })]);
    expect(manager.get(KEY)).toEqual({ a: 2 });
  });

  it('queues the re-send when the network fails during the retry', async () => {
    editLocally({ a: 1 }, { a: 2 });
    serverHolds({ a: 3 }, deviceId);
    sync.mockResolvedValueOnce(conflictOn(KEY)).mockRejectedValueOnce(new Error('socket closed'));
    vi.spyOn(console, 'warn').mockImplementation(() => {});

    await manager.forceSync();

    expect(JSON.parse(String(localStorageMock.getItem(OFFLINE_QUEUE_KEY)))).toEqual([
      expect.objectContaining({ key: KEY, value: { a: 2 } }),
    ]);
  });

  it('adopts the server record for a conflicting key it holds no local value for', async () => {
    editLocally({ a: 1 }, { a: 2 });
    get.mockResolvedValue(record('personalSettings', { theme: 1 }, '1000_5', 'dev-remote'));
    sync.mockResolvedValueOnce(conflictOn('personalSettings'));
    const personalListener = vi.fn();
    manager.subscribe('personalSettings', personalListener);

    await manager.forceSync();

    expect(manager.get('personalSettings')).toEqual({ theme: 1 });
    expect(personalListener).toHaveBeenCalledWith('personalSettings', { theme: 1 }, expect.anything());
    expect(sync).toHaveBeenCalledTimes(1);
  });

  it('does nothing for a conflicting key the server no longer has', async () => {
    editLocally({ a: 1 }, { a: 2 });
    get.mockResolvedValue(null);
    sync.mockResolvedValueOnce(conflictOn(KEY));

    await manager.forceSync();

    expect(sync).toHaveBeenCalledTimes(1);
    expect(manager.get(KEY)).toEqual({ a: 2 });
  });
});
