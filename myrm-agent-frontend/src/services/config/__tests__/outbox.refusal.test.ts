/**
 * The backend validates a whole batch before it stores any change, so a batch it refuses outright says nothing about
 * which change it dislikes: each key is sent alone, only the keys it refuses lose their write, and the caller of
 * `forceSync()` still sees the refusal.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ConfigSyncManager, getConfigSyncManager, resetConfigSyncManager } from '@/services/config/ConfigSyncManager';
import type { ConfigChange, ConfigKey, ConfigRecord, SyncResult } from '@/services/config/types';
import { serveCloudBackend, storedKeys } from './fakeCloudBackend';
import type { RecordedWrite } from './fakeCloudBackend';

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

const POISON: ConfigKey = 'providers';
const sentKeys = (writes: RecordedWrite[]) => writes.map((write) => write.changes.map((change) => change.key));
const mergeBaseVersion = (manager: ConfigSyncManager, key: ConfigKey) =>
  (Reflect.get(manager, 'baseCache') as Map<ConfigKey, ConfigRecord>).get(key)?.meta.version;

describe('config outbox refused writes (cloud mode)', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.spyOn(console, 'warn').mockImplementation(() => {});
    resetConfigSyncManager();
    localStorage.clear();
  });

  afterEach(() => {
    resetConfigSyncManager();
    vi.clearAllTimers();
    vi.useRealTimers();
    vi.restoreAllMocks();
    localStorage.clear();
  });

  const editThreeKeys = async () => {
    const manager = getConfigSyncManager();
    await manager.initialize();
    manager.set('chatSettings', { a: 1 } as never);
    manager.set(POISON, { p: 1 } as never);
    manager.set('personalSettings', { c: 1 } as never);
    return manager;
  };

  it.each([422, 500])(
    'takes the keys of a batch refused with %i one by one, dropping only the refused one',
    async (status) => {
      const writes = serveCloudBackend({
        answer: (changes) => (changes.some((change) => change.key === POISON) ? status : 'accept'),
      });
      const manager = await editThreeKeys();

      await expect(manager.forceSync()).rejects.toThrow('Failed to sync configs');

      expect(sentKeys(writes)).toEqual([
        ['chatSettings', POISON, 'personalSettings'],
        ['chatSettings'],
        [POISON],
        ['personalSettings'],
      ]);
      expect(mergeBaseVersion(manager, 'chatSettings')).toBe('2000_0');
      expect(mergeBaseVersion(manager, 'personalSettings')).toBe('2000_0');
      expect(mergeBaseVersion(manager, POISON)).toBe('1000_0');
      expect(manager.status).toBe('error');
      expect(storedKeys()).toEqual([]);
    },
  );

  it('does not retry the refused key, and does not hold the other keys back', async () => {
    const writes = serveCloudBackend({
      answer: (changes) => (changes.some((change) => change.key === POISON) ? 422 : 'accept'),
    });
    const manager = await editThreeKeys();
    await expect(manager.forceSync()).rejects.toThrow();

    await vi.advanceTimersByTimeAsync(120_000);
    expect(writes).toHaveLength(4);

    manager.set('chatSettings', { a: 2 } as never);
    await vi.advanceTimersByTimeAsync(1100);
    expect(sentKeys(writes).at(-1)).toEqual(['chatSettings']);
    expect(manager.getRecord('chatSettings')?.meta.version).toBe('2000_0');
  });

  it('reports a batch that was refused as a whole but taken key by key as taken', async () => {
    serveCloudBackend({ answer: (changes) => (changes.length > 1 ? 500 : 'accept') });
    const manager = await editThreeKeys();

    await expect(manager.forceSync()).resolves.toMatchObject({ success: true, conflicts: [] });

    for (const key of ['chatSettings', POISON, 'personalSettings'] as const) {
      expect(manager.getRecord(key)?.meta.version).toBe('2000_0');
    }
    expect(manager.status).toBe('idle');
  });

  it('does not send a refused single change a second time', async () => {
    const writes = serveCloudBackend({ answer: () => 422 });
    const manager = getConfigSyncManager();
    await manager.initialize();
    manager.set(POISON, { p: 1 } as never);

    await expect(manager.forceSync()).rejects.toThrow('Failed to sync configs');

    expect(sentKeys(writes)).toEqual([[POISON]]);
    expect(manager.status).toBe('error');
  });
});

describe('config outbox refusal next to a clash', () => {
  const DEVICE = 'dev-local';
  const CLASHING: ConfigKey = 'chatSettings';
  const REFUSED: ConfigKey = 'commands';
  const TAKEN: ConfigKey = 'channels';

  const record = (key: ConfigKey, value: Record<string, number>, version: string, deviceId = DEVICE): ConfigRecord => ({
    key,
    value: value as never,
    meta: { version, updatedAt: '2026-01-01T00:00:00.000Z', deviceId },
  });

  beforeEach(() => {
    vi.useFakeTimers();
    vi.spyOn(console, 'warn').mockImplementation(() => {});
    resetConfigSyncManager();
    localStorage.clear();
  });

  afterEach(() => {
    resetConfigSyncManager();
    vi.clearAllTimers();
    vi.useRealTimers();
    vi.restoreAllMocks();
    localStorage.clear();
  });

  const refusal = new Error('Failed to sync configs: Unprocessable Entity');

  /**
   * A backend that refuses every batch of more than one key and, key by key, refuses REFUSED, clashes on CLASHING
   * (a change another device made) and takes TAKEN. The caller edits the given keys, in that order.
   */
  const install = (resolver: () => Promise<boolean> | boolean, ...edited: ConfigKey[]) => {
    const sync = vi.fn((changes: ConfigChange[]): Promise<SyncResult> => {
      const [only] = changes;
      if (changes.length > 1 || only?.key === REFUSED) {
        return Promise.reject(refusal);
      }
      const taken = only?.key === TAKEN;
      return Promise.resolve({
        success: taken,
        conflicts: taken ? [] : [CLASHING],
        newVersions: new Map(taken ? [[TAKEN, '2000_0']] : []),
      });
    });
    const manager = getConfigSyncManager();
    const confirmed = () => new Map([CLASHING, REFUSED, TAKEN].map((key) => [key, record(key, { a: 1 }, '1000_0')]));
    const serverRecord = record(CLASHING, { a: 3 }, '1000_5', 'dev-remote');
    Object.assign(manager, {
      adapter: { getDeviceId: () => DEVICE, sync, get: vi.fn().mockResolvedValue(serverRecord) },
      cache: confirmed(),
      baseCache: confirmed(),
      _isInitialized: true,
    });
    manager.setConflictResolver(resolver);
    for (const key of edited) {
      manager.set(key, { a: 2 } as never);
    }
    return { manager, sentKeys: () => sync.mock.calls.map(([changes]) => changes.map((change) => change.key)) };
  };

  it('reports the refusal only after the clash raised by another key of the batch is settled', async () => {
    let decide: (keepLocal: boolean) => void = () => {};
    const resolver = vi.fn(() => new Promise<boolean>((resolve) => (decide = resolve)));
    const { manager, sentKeys } = install(resolver, CLASHING, REFUSED, TAKEN);

    const outcome = manager.forceSync().then(
      () => 'taken',
      (error: unknown) => error,
    );
    await vi.advanceTimersByTimeAsync(0);
    expect(resolver).toHaveBeenCalledTimes(1);
    expect(await Promise.race([outcome, 'still waiting'])).toBe('still waiting');

    decide(false);
    expect(await outcome).toBe(refusal);
    expect(sentKeys()).toEqual([[CLASHING, REFUSED, TAKEN], [CLASHING], [REFUSED], [TAKEN]]);
    expect(mergeBaseVersion(manager, TAKEN)).toBe('2000_0');
  });

  it('answers a batch refused as a whole with what its keys answered one by one', async () => {
    const { manager } = install(() => false, CLASHING, TAKEN);

    await expect(manager.forceSync()).resolves.toEqual({
      success: false,
      conflicts: [CLASHING],
      newVersions: new Map([[TAKEN, '2000_0']]),
    });
  });
});
