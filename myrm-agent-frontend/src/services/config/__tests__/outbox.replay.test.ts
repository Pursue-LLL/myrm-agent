/**
 * Replay of the changes a previous session left behind: each change is judged on its own against what the server
 * holds (nothing is made up), only what still has to reach the server is sent, and a change leaves the store once it
 * is settled, not before.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { getConfigSyncManager, resetConfigSyncManager } from '@/services/config/ConfigSyncManager';
import type { ConfigConflictResolution } from '@/services/config/conflictResolution';
import { saveOfflineQueue } from '@/services/config/offlineQueue';
import type { ConfigOutbox } from '@/services/config/outbox';
import type { ConfigChange, ConfigKey } from '@/services/config/types';
import { OFFLINE_QUEUE_KEY, serveCloudBackend, storedKeys } from './fakeCloudBackend';
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

/** A change left by an earlier session, based on server version `1000_5` unless said otherwise. */
const leftover = (key: ConfigKey, value: object, expectedVersion = '1000_5', timestamp = 1): ConfigChange => ({
  key,
  value: value as never,
  expectedVersion,
  timestamp,
});
const sentKeys = (writes: RecordedWrite[]) => writes.flatMap((write) => write.changes.map((change) => change.key));
const askedKeys = (resolver: { mock: { calls: Array<[ConfigConflictResolution]> } }) =>
  resolver.mock.calls.map(([conflict]) => conflict.configKey);

describe('replay of leftover changes (cloud mode)', () => {
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

  it('settles a change the server already holds, without asking and without sending', async () => {
    const writes = serveCloudBackend({ rows: { chatSettings: { value: { n: 7 }, version: '2000_0' } } });
    saveOfflineQueue([leftover('chatSettings', { n: 7 })]);
    const resolver = vi.fn(() => true);
    const manager = getConfigSyncManager();
    manager.setConflictResolver(resolver);

    await manager.initialize();

    expect(resolver).not.toHaveBeenCalled();
    expect(writes).toEqual([]);
    expect(storedKeys()).toEqual([]);
    expect(manager.get('chatSettings')).toEqual({ n: 7 });
  });

  it('sends a change for a key the server has no row for, without asking', async () => {
    const writes = serveCloudBackend();
    saveOfflineQueue([leftover('commands', { c: 1 })]);
    const resolver = vi.fn(() => false);
    const manager = getConfigSyncManager();
    manager.setConflictResolver(resolver);

    await manager.initialize();

    expect(resolver).not.toHaveBeenCalled();
    expect(sentKeys(writes)).toEqual(['commands']);
    expect(storedKeys()).toEqual([]);
  });

  it('asks about each stale change on its own and acts on each answer', async () => {
    const writes = serveCloudBackend({
      rows: {
        chatSettings: { value: { n: 1 }, version: '2000_0', deviceId: 'web' },
        personalSettings: { value: { marker: 'SERVER' }, version: '2000_0' },
      },
    });
    saveOfflineQueue([
      leftover('chatSettings', { n: 7 }, '1000_5', 1),
      leftover('personalSettings', { marker: 'LOCAL' }, '1000_5', 2),
    ]);
    const resolver = vi.fn(({ configKey }: ConfigConflictResolution) => configKey === 'chatSettings');
    const manager = getConfigSyncManager();
    manager.setConflictResolver(resolver);

    await manager.initialize();

    expect(askedKeys(resolver)).toEqual(['chatSettings', 'personalSettings']);
    expect(sentKeys(writes)).toEqual(['chatSettings']);
    expect(manager.get('personalSettings')).toEqual({ marker: 'SERVER' });
    expect(storedKeys()).toEqual([]);
  });

  it('shows the user what the server holds, and sends a change the user keeps against that version', async () => {
    const writes = serveCloudBackend({
      rows: { chatSettings: { value: { n: 1 }, version: '2000_0', deviceId: 'web' } },
    });
    saveOfflineQueue([leftover('chatSettings', { n: 7 })]);
    const resolver = vi.fn(() => true);
    const manager = getConfigSyncManager();
    manager.setConflictResolver(resolver);

    await manager.initialize();

    expect(resolver).toHaveBeenCalledExactlyOnceWith({
      configKey: 'chatSettings',
      localVersion: '1000_5',
      serverVersion: '2000_0',
      deviceId: 'web',
      localValue: { n: 7 },
      serverValue: { n: 1 },
    });
    expect(writes).toHaveLength(1);
    expect(writes[0]?.changes).toEqual([expect.objectContaining({ key: 'chatSettings', expectedVersion: '2000_0' })]);
    expect(manager.get('chatSettings')).toEqual({ n: 7 });
  });

  it('lets the server win a stale change when nobody can be asked', async () => {
    const writes = serveCloudBackend({ rows: { chatSettings: { value: { n: 1 }, version: '2000_0' } } });
    saveOfflineQueue([leftover('chatSettings', { n: 7 })]);
    const manager = getConfigSyncManager();

    await manager.initialize();

    expect(writes).toEqual([]);
    expect(storedKeys()).toEqual([]);
    expect(manager.get('chatSettings')).toEqual({ n: 1 });
  });

  it('lets the server win a stale change when the resolver fails', async () => {
    const writes = serveCloudBackend({ rows: { chatSettings: { value: { n: 1 }, version: '2000_0' } } });
    saveOfflineQueue([leftover('chatSettings', { n: 7 })]);
    const manager = getConfigSyncManager();
    manager.setConflictResolver(() => Promise.reject(new Error('dialog crashed')));

    await manager.initialize();

    expect(writes).toEqual([]);
    expect(storedKeys()).toEqual([]);
    expect(manager.get('chatSettings')).toEqual({ n: 1 });
  });

  it('replays an entry lifted out of storage once, so it does not come back as a stale question later', async () => {
    const writes = serveCloudBackend();
    // `providers` may not wait in browser storage: a copy an earlier client left there is lifted into memory.
    localStorage.setItem(OFFLINE_QUEUE_KEY, JSON.stringify([leftover('providers', { p: 1 }, '1000_0')]));
    const resolver = vi.fn(() => true);
    const manager = getConfigSyncManager();
    manager.setConflictResolver(resolver);
    await manager.initialize();
    expect(sentKeys(writes)).toEqual(['providers']);
    expect(localStorage.getItem(OFFLINE_QUEUE_KEY)).toBeNull();

    manager.set('providers', { p: 2 } as never);
    await vi.advanceTimersByTimeAsync(1100);
    window.dispatchEvent(new Event('online'));
    await vi.advanceTimersByTimeAsync(10);

    expect(resolver).not.toHaveBeenCalled();
    expect(sentKeys(writes)).toEqual(['providers', 'providers']);
  });

  it('keeps an edit made while the user is being asked', async () => {
    const writes = serveCloudBackend({ rows: { chatSettings: { value: { n: 1 }, version: '2000_0' } } });
    saveOfflineQueue([leftover('chatSettings', { n: 7 })]);
    let decide: (keepLocal: boolean) => void = () => {};
    const resolver = vi.fn(() => new Promise<boolean>((resolve) => (decide = resolve)));
    const manager = getConfigSyncManager();
    manager.setConflictResolver(resolver);
    const starting = manager.initialize();
    await vi.waitFor(() => expect(resolver).toHaveBeenCalledOnce());

    manager.set('personalSettings', { marker: 'LIVE' } as never);
    decide(true);
    await starting;
    await vi.advanceTimersByTimeAsync(1100);

    expect(sentKeys(writes).sort()).toEqual(['chatSettings', 'personalSettings']);
  });

  it('keeps a change whose key the server cannot be asked about, and sends the others', async () => {
    const failingReads: Record<string, number> = { commands: 401 };
    const writes = serveCloudBackend({ failingReads });
    saveOfflineQueue([leftover('commands', { c: 1 }), leftover('channels', { x: 1 })]);
    const resolver = vi.fn(() => false);
    const manager = getConfigSyncManager();
    manager.setConflictResolver(resolver);

    await manager.initialize();

    expect(resolver).not.toHaveBeenCalled();
    expect(sentKeys(writes)).toEqual(['channels']);
    expect(storedKeys()).toEqual(['commands']);
    expect(manager.status).toBe('offline');

    delete failingReads.commands;
    window.dispatchEvent(new Event('online'));
    await vi.advanceTimersByTimeAsync(10);

    expect(sentKeys(writes)).toEqual(['channels', 'commands']);
    expect(storedKeys()).toEqual([]);
    expect(manager.status).toBe('idle');
  });

  it('keeps a replayed change stored while it is on the wire and until the backend has taken it', async () => {
    const backend = { up: false };
    const storedWhenSent: string[][] = [];
    serveCloudBackend({
      rows: { chatSettings: { value: { n: 1 }, version: '1000_5' } },
      answer: () => {
        storedWhenSent.push(storedKeys());
        return backend.up ? 'accept' : 503;
      },
    });
    saveOfflineQueue([leftover('chatSettings', { n: 7 })]);
    const manager = getConfigSyncManager();

    await manager.initialize();
    expect(storedKeys()).toEqual(['chatSettings']);

    backend.up = true;
    await vi.advanceTimersByTimeAsync(1000);
    expect(storedKeys()).toEqual([]);
    expect(storedWhenSent).toEqual([['chatSettings'], ['chatSettings']]);
  });

  it('leaves out of a replay what the queue already holds: the same edit or a newer one of the key', () => {
    const outbox = (getConfigSyncManager() as unknown as { outbox: ConfigOutbox }).outbox;
    saveOfflineQueue([
      leftover('chatSettings', { n: 1 }, '1000_0', 5),
      leftover('channels', { x: 1 }, '1000_0', 5),
      leftover('commands', { c: 1 }, '1000_0', 5),
    ]);
    Object.assign(outbox, {
      queue: [leftover('chatSettings', { n: 2 }, '1000_0', 6), leftover('channels', { x: 1 }, '1000_0', 5)],
    });

    expect(outbox.collectOfflineChanges().map((change) => change.key)).toEqual(['commands']);
  });
});
