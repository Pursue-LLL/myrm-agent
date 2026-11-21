import { beforeEach, describe, expect, it, vi } from 'vitest';
import {
  isRecoverableSyncError,
  loadOfflineQueue,
  removeOfflineEntries,
  saveOfflineQueue,
} from '@/services/config/offlineQueue';
import type { ConfigChange } from '@/services/config/types';

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

const change = (key: ConfigChange['key'], value: unknown, expectedVersion: string, timestamp = 1): ConfigChange => ({
  key,
  value: value as never,
  expectedVersion,
  timestamp,
});

describe('offline queue storage', () => {
  beforeEach(() => {
    localStorageMock.clear();
  });

  it('writes only allowlisted keys and nothing at all when none qualify', () => {
    saveOfflineQueue([change('providers', { secret: 'x' }, '1000_0')]);
    expect(localStorageMock.setItem).not.toHaveBeenCalled();

    saveOfflineQueue([change('providers', { secret: 'x' }, '1000_0'), change('chatSettings', { a: 1 }, '1000_0')]);
    expect(loadOfflineQueue().map((queued) => queued.key)).toEqual(['chatSettings']);
  });

  it('keeps the latest value but the earliest base version when a key is queued twice', () => {
    saveOfflineQueue([change('chatSettings', { a: 1 }, '1000_0')]);
    saveOfflineQueue([change('chatSettings', { a: 2 }, '1000_3')]);

    expect(loadOfflineQueue()).toEqual([expect.objectContaining({ value: { a: 2 }, expectedVersion: '1000_0' })]);
  });

  it('judges which value is the latest by edit time, not by the order the entries arrive in', () => {
    saveOfflineQueue([change('chatSettings', { a: 2 }, '1000_1', 5)]);
    saveOfflineQueue([change('chatSettings', { a: 1 }, '1000_0', 3)]);

    expect(loadOfflineQueue()).toEqual([
      expect.objectContaining({ value: { a: 2 }, expectedVersion: '1000_0', timestamp: 5 }),
    ]);
  });

  it('reads an unreadable stored queue as empty', () => {
    localStorageMock.setItem('config-offline-queue', '{not json');
    expect(loadOfflineQueue()).toEqual([]);
  });
});

describe('settled entries leave the offline queue', () => {
  beforeEach(() => {
    localStorageMock.clear();
    vi.clearAllMocks();
  });

  it('removes the stored copy of a settled key and leaves every other key queued', () => {
    saveOfflineQueue([change('chatSettings', { a: 1 }, '1000_0'), change('securityConfig', { s: 1 }, '1000_0')]);

    removeOfflineEntries([change('chatSettings', { a: 1 }, '1000_0')]);

    expect(loadOfflineQueue().map((queued) => queued.key)).toEqual(['securityConfig']);
  });

  it('removes an older stored copy of a settled key too', () => {
    saveOfflineQueue([change('chatSettings', { a: 1 }, '1000_0', 2)]);

    removeOfflineEntries([change('chatSettings', { a: 2 }, '1000_0', 3)]);

    expect(localStorageMock.getItem('config-offline-queue')).toBeNull();
  });

  it('keeps a newer edit of the settled key', () => {
    saveOfflineQueue([change('chatSettings', { a: 2 }, '1000_0', 5)]);

    removeOfflineEntries([change('chatSettings', { a: 1 }, '1000_0', 3)]);

    expect(loadOfflineQueue()).toEqual([expect.objectContaining({ value: { a: 2 }, timestamp: 5 })]);
  });

  it('tells two edits of the same millisecond apart by their value', () => {
    saveOfflineQueue([change('chatSettings', { a: 2 }, '1000_0', 4)]);

    removeOfflineEntries([change('chatSettings', { a: 1 }, '1000_0', 4)]);
    expect(loadOfflineQueue()).toHaveLength(1);

    removeOfflineEntries([change('chatSettings', { a: 2 }, '1000_0', 4)]);
    expect(loadOfflineQueue()).toEqual([]);
  });

  it('writes nothing when no stored entry is covered', () => {
    saveOfflineQueue([change('chatSettings', { a: 1 }, '1000_0')]);
    vi.clearAllMocks();

    removeOfflineEntries([change('securityConfig', { s: 1 }, '1000_0')]);

    expect(localStorageMock.setItem).not.toHaveBeenCalled();
    expect(localStorageMock.removeItem).not.toHaveBeenCalled();
  });
});

describe('offline failure classification', () => {
  it('treats the backend-unavailable result and network or offline messages as transient', () => {
    expect(isRecoverableSyncError('Backend not available')).toBe(true);
    expect(isRecoverableSyncError('You are OFFLINE')).toBe(true);
    expect(isRecoverableSyncError('Validation failed')).toBe(false);
  });
});
