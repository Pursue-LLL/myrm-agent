/**
 * How the write path sends: one batch in flight at a time, each answer settles only the keys it names, and what a
 * newer edit or another key still has queued survives that answer.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ConfigSyncManager, getConfigSyncManager, resetConfigSyncManager } from '@/services/config/ConfigSyncManager';
import type { ConfigChange, ConfigKey, ConfigRecord, SyncResult } from '@/services/config/types';

const KEY: ConfigKey = 'chatSettings';
const SECURITY: ConfigKey = 'securityConfig';
const OTHER: ConfigKey = 'commands';
const DEVICE = 'dev-local';
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

const record = (key: ConfigKey, value: Doc, version: string, deviceId = DEVICE): ConfigRecord => ({
  key,
  value: value as never,
  meta: { version, updatedAt: '2026-01-01T00:00:00.000Z', deviceId },
});

const accepted = (...versions: Array<[ConfigKey, string]>): SyncResult => ({
  success: true,
  conflicts: [],
  newVersions: new Map(versions),
});
const conflictOn = (conflicts: ConfigKey[], ...versions: Array<[ConfigKey, string]>): SyncResult => ({
  success: false,
  conflicts,
  newVersions: new Map(versions),
});

const storedQueue = () => {
  const raw = localStorageMock.getItem(OFFLINE_QUEUE_KEY);
  return raw ? (JSON.parse(raw) as ConfigChange[]) : [];
};
const settleMicrotasks = () => vi.advanceTimersByTimeAsync(0);

describe('config outbox sending', () => {
  let manager: ConfigSyncManager;
  /** Requests the backend has received; the test releases each answer. */
  let requests: Array<{ changes: ConfigChange[]; answer: (result: SyncResult) => void }>;
  let get: ReturnType<typeof vi.fn>;

  const base = (...rows: Array<[ConfigKey, Doc, string]>) => {
    const confirmed = () => new Map(rows.map(([key, value, version]) => [key, record(key, value, version)]));
    const sync = (changes: ConfigChange[]) =>
      new Promise<SyncResult>((answer) => requests.push({ changes: structuredClone(changes), answer }));
    Object.assign(manager, {
      adapter: { getDeviceId: () => DEVICE, sync: vi.fn(sync), get },
      cache: confirmed(),
      baseCache: confirmed(),
      _isInitialized: true,
    });
  };
  const mergeBase = (key: ConfigKey) => (Reflect.get(manager, 'baseCache') as Map<ConfigKey, ConfigRecord>).get(key);
  /** Answers the request with that index, waiting for it to reach the backend first. */
  const answer = async (index: number, result: SyncResult) => {
    await vi.waitFor(() => expect(requests[index]).toBeDefined());
    requests[index]?.answer(result);
    await settleMicrotasks();
  };

  beforeEach(() => {
    vi.useFakeTimers();
    localStorageMock.clear();
    resetConfigSyncManager();
    manager = getConfigSyncManager();
    requests = [];
    get = vi.fn();
    vi.spyOn(console, 'warn').mockImplementation(() => {});
  });

  afterEach(() => {
    resetConfigSyncManager();
    vi.clearAllTimers();
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it('holds an edit made while a write is in flight until the answer, then sends it on the version that answer returned', async () => {
    base([SECURITY, { s: 0 }, '1000_0']);
    manager.set(SECURITY, { s: 1 } as never);
    await settleMicrotasks();
    manager.set(SECURITY, { s: 2 } as never);
    await settleMicrotasks();

    expect(requests).toHaveLength(1);

    await answer(0, accepted([SECURITY, '2000_0']));
    await vi.waitFor(() => expect(requests).toHaveLength(2));

    expect(requests[1]?.changes).toEqual([
      expect.objectContaining({ key: SECURITY, value: { s: 2 }, expectedVersion: '2000_0' }),
    ]);
    await answer(1, accepted([SECURITY, '3000_0']));
    expect(manager.getRecord(SECURITY)?.meta.version).toBe('3000_0');
    expect(get).not.toHaveBeenCalled();
  });

  it('keeps the newer value on screen when the answer to an older write arrives', async () => {
    base([KEY, { a: 0 }, '1000_0']);
    manager.set(KEY, { a: 1 } as never);
    const first = manager.forceSync();
    await settleMicrotasks();
    manager.set(KEY, { a: 2 } as never);

    await answer(0, accepted([KEY, '2000_0']));

    expect(manager.get(KEY)).toEqual({ a: 2 });
    expect(mergeBase(KEY)).toMatchObject({ value: { a: 1 }, meta: { version: '2000_0' } });
    await first;
  });

  it('acknowledges only the keys it names: the stored copy of another key that is still queued stays', async () => {
    base([KEY, { a: 0 }, '1000_0'], [SECURITY, { s: 0 }, '1000_0']);
    manager.set(KEY, { a: 1 } as never);
    const flushing = manager.forceSync();
    await settleMicrotasks();
    manager.set(SECURITY, { s: 1 } as never);
    await settleMicrotasks();
    expect(storedQueue().map((entry) => entry.key)).toEqual([SECURITY]);

    await answer(0, accepted([KEY, '2000_0']));

    expect(storedQueue().map((entry) => entry.key)).toEqual([SECURITY]);
    await answer(1, accepted([SECURITY, '2000_0']));
    expect(storedQueue()).toEqual([]);
    await flushing;
  });

  it('drops an older stored copy of a key once a newer value of it has been accepted', async () => {
    base([KEY, { a: 0 }, '1000_0']);
    localStorageMock.setItem(
      OFFLINE_QUEUE_KEY,
      JSON.stringify([{ key: KEY, value: { a: 1 }, expectedVersion: '1000_0', timestamp: 1 }]),
    );
    manager.set(KEY, { a: 2 } as never);
    const flushing = manager.forceSync();
    await settleMicrotasks();

    await answer(0, accepted([KEY, '2000_0']));

    expect(storedQueue()).toEqual([]);
    await flushing;
  });

  it('settles the keys a mixed answer accepted, and asks about the one that clashed', async () => {
    base([KEY, { a: 1 }, '1000_0'], [OTHER, { c: 1 }, '1000_0']);
    get.mockResolvedValue(record(KEY, { a: 3 }, '1000_5'));
    manager.set(KEY, { a: 2 } as never);
    manager.set(OTHER, { c: 2 } as never);
    const flushing = manager.forceSync();
    await settleMicrotasks();

    await answer(0, conflictOn([KEY], [OTHER, '2000_0']));
    await answer(1, accepted([KEY, '2000_1']));
    await flushing;

    expect(mergeBase(OTHER)).toMatchObject({ value: { c: 2 }, meta: { version: '2000_0' } });
    expect(requests[1]?.changes).toEqual([expect.objectContaining({ key: KEY, expectedVersion: '1000_5' })]);
    expect(mergeBase(KEY)).toMatchObject({ value: { a: 2 }, meta: { version: '2000_1' } });
  });

  it('keeps a change queued, and stored, when the answer neither accepts it nor names a clash on it', async () => {
    base([KEY, { a: 1 }, '1000_0'], [OTHER, { c: 1 }, '1000_0']);
    get.mockResolvedValue(record(KEY, { a: 3 }, '1000_5'));
    manager.set(KEY, { a: 2 } as never);
    manager.set(OTHER, { c: 2 } as never);
    const flushing = manager.forceSync();
    await settleMicrotasks();

    await answer(0, conflictOn([KEY]));
    await answer(1, accepted([KEY, '2000_1']));
    await flushing;

    expect(storedQueue()).toEqual([
      expect.objectContaining({ key: OTHER, value: { c: 2 }, expectedVersion: '1000_0' }),
    ]);
    await vi.advanceTimersByTimeAsync(1100);
    expect(requests[2]?.changes).toEqual([expect.objectContaining({ key: OTHER, value: { c: 2 } })]);
  });

  it('keeps a clashing change queued, and stored, when the server cannot be asked about it', async () => {
    base([KEY, { a: 1 }, '1000_0']);
    get.mockRejectedValue(new Error('Backend not available'));
    manager.set(KEY, { a: 2 } as never);
    const flushing = manager.forceSync();
    await settleMicrotasks();

    await answer(0, conflictOn([KEY]));
    await flushing;

    expect(storedQueue()).toEqual([expect.objectContaining({ key: KEY, value: { a: 2 }, expectedVersion: '1000_0' })]);
    expect(manager.get(KEY)).toEqual({ a: 2 });
  });

  it('queues a write the backend could not take behind newer edits of the same key', async () => {
    base([SECURITY, { s: 0 }, '1000_0']);
    manager.set(SECURITY, { s: 1 } as never);
    await settleMicrotasks();
    manager.set(SECURITY, { s: 2 } as never);
    await settleMicrotasks();

    await answer(0, { success: false, conflicts: [], newVersions: new Map(), error: 'Backend not available' });

    expect(storedQueue()).toEqual([expect.objectContaining({ value: { s: 2 }, expectedVersion: '1000_0' })]);
    await vi.advanceTimersByTimeAsync(1100);
    expect(requests).toHaveLength(2);
    expect(requests[1]?.changes).toEqual([
      expect.objectContaining({ key: SECURITY, value: { s: 2 }, expectedVersion: '1000_0' }),
    ]);
  });

  it('records the re-sent value as the merge base once the server accepted it', async () => {
    base([KEY, { a: 1 }, '1000_0']);
    get.mockResolvedValue(record(KEY, { a: 3 }, '1000_5', 'dev-remote'));
    manager.setConflictResolver(() => true);
    manager.set(KEY, { a: 2 } as never);
    const flushing = manager.forceSync();
    await settleMicrotasks();

    await answer(0, conflictOn([KEY]));
    await answer(1, accepted([KEY, '1000_9']));
    await flushing;

    expect(mergeBase(KEY)).toMatchObject({ value: { a: 2 }, meta: { version: '1000_9' } });
  });

  it('does not retry a change the backend answered with an application error, and forgets its stored copy', async () => {
    base([SECURITY, { s: 0 }, '1000_0']);
    manager.set(SECURITY, { s: 1 } as never);
    await settleMicrotasks();

    await answer(0, { success: false, conflicts: [], newVersions: new Map(), error: 'Validation failed' });
    await vi.advanceTimersByTimeAsync(120_000);

    expect(requests).toHaveLength(1);
    expect(manager.status).toBe('error');
    expect(storedQueue()).toEqual([]);
  });

  describe('while the user is asked about a clash', () => {
    let decide: (keepLocal: boolean) => void;

    const openClash = async (clashing: ConfigKey = KEY) => {
      base([KEY, { a: 1 }, '1000_0'], [SECURITY, { s: 0 }, '1000_0']);
      get.mockResolvedValue(record(clashing, { a: 3 }, '1000_5', 'dev-remote'));
      manager.setConflictResolver(() => new Promise<boolean>((resolve) => (decide = resolve)));
      manager.set(clashing, { a: 2 } as never);
      void manager.forceSync();
      await settleMicrotasks();
      await answer(0, conflictOn([clashing]));
      await vi.waitFor(() => expect(decide).toBeTypeOf('function'));
    };

    it('sends a write to another key at once', async () => {
      await openClash();

      manager.set(SECURITY, { s: 1 } as never);
      await settleMicrotasks();

      expect(requests[1]?.changes).toEqual([expect.objectContaining({ key: SECURITY, value: { s: 1 } })]);
      await answer(1, accepted([SECURITY, '2000_0']));
      decide(true);
    });

    it('holds a newer edit of the clashing key until the answer, then sends it on the version the settlement produced', async () => {
      await openClash();

      manager.set(KEY, { a: 5 } as never);
      await vi.advanceTimersByTimeAsync(1500);
      expect(requests).toHaveLength(1);

      decide(true);
      await answer(1, accepted([KEY, '1000_9']));

      expect(requests[1]?.changes).toEqual([expect.objectContaining({ key: KEY, expectedVersion: '1000_5' })]);
      await vi.advanceTimersByTimeAsync(1100);
      expect(requests).toHaveLength(3);
      expect(requests[2]?.changes).toEqual([
        expect.objectContaining({ key: KEY, value: { a: 5 }, expectedVersion: '1000_9' }),
      ]);
      await answer(2, accepted([KEY, '1000_10']));
      expect(manager.get(KEY)).toEqual({ a: 5 });
    });

    it('lets the re-send settle only the stored copies of the edits it carries', async () => {
      await openClash(SECURITY);
      manager.set(SECURITY, { a: 5 } as never);
      await vi.advanceTimersByTimeAsync(5000);

      decide(true);
      await answer(1, accepted([SECURITY, '1000_9']));

      expect(storedQueue()).toEqual([expect.objectContaining({ key: SECURITY, value: { a: 5 } })]);
    });

    it('keeps the stored copy of a kept value until the backend has taken the re-send', async () => {
      await openClash(SECURITY);

      decide(true);
      await vi.waitFor(() => expect(requests).toHaveLength(2));
      expect(storedQueue()).toEqual([expect.objectContaining({ key: SECURITY })]);

      await answer(1, accepted([SECURITY, '1000_9']));
      expect(storedQueue()).toEqual([]);
    });

    it('sends the kept value after the write in flight, never beside it', async () => {
      await openClash();
      manager.set(SECURITY, { s: 1 } as never);
      await settleMicrotasks();
      expect(requests).toHaveLength(2);

      decide(true);
      await settleMicrotasks();
      expect(requests).toHaveLength(2);

      await answer(1, accepted([SECURITY, '2000_0']));
      await vi.waitFor(() => expect(requests).toHaveLength(3));
      expect(requests[2]?.changes).toEqual([expect.objectContaining({ key: KEY })]);
    });

    describe('after an edit queued behind the write that clashed', () => {
      /** SECURITY is edited twice: the second edit waits behind the write in flight, and both are stored at once. */
      const clashBehindQueuedEdit = async () => {
        base([SECURITY, { s: 0 }, '1000_0']);
        get.mockResolvedValue(record(SECURITY, { s: 3 }, '1000_5', 'dev-remote'));
        let answerUser: (keepLocal: boolean) => void = () => undefined;
        const asked = vi.fn(() => new Promise<boolean>((resolve) => (answerUser = resolve)));
        manager.setConflictResolver(asked);
        manager.set(SECURITY, { s: 1 } as never);
        await settleMicrotasks();
        manager.set(SECURITY, { s: 2 } as never);
        await settleMicrotasks();
        await answer(0, conflictOn([SECURITY]));
        await vi.waitFor(() => expect(asked).toHaveBeenCalledTimes(1));
        return (keepLocal: boolean) => answerUser(keepLocal);
      };

      it('lets the re-send settle the stored copy of that edit too, since it carries its value', async () => {
        const answerUser = await clashBehindQueuedEdit();

        answerUser(true);
        await answer(1, accepted([SECURITY, '1000_9']));

        expect(requests[1]?.changes).toEqual([expect.objectContaining({ key: SECURITY, value: { s: 2 } })]);
        expect(storedQueue()).toEqual([]);
      });

      it('lets the server value win over every edit the user was shown, and forgets their stored copies', async () => {
        const answerUser = await clashBehindQueuedEdit();

        answerUser(false);
        await vi.advanceTimersByTimeAsync(5000);

        expect(requests).toHaveLength(1);
        expect(storedQueue()).toEqual([]);
        expect(manager.get(SECURITY)).toEqual({ s: 3 });
      });

      it('keeps an edit made after the question was asked when the server value wins', async () => {
        const answerUser = await clashBehindQueuedEdit();
        manager.set(SECURITY, { s: 4 } as never);
        await settleMicrotasks();

        answerUser(false);
        await vi.advanceTimersByTimeAsync(1100);

        expect(requests).toHaveLength(2);
        expect(requests[1]?.changes).toEqual([
          expect.objectContaining({ key: SECURITY, value: { s: 4 }, expectedVersion: '1000_5' }),
        ]);
        expect(storedQueue()).toEqual([expect.objectContaining({ key: SECURITY, value: { s: 4 } })]);
      });
    });
  });
});
