import { beforeEach, describe, expect, it, vi } from 'vitest';
import {
  clearOfflineQueue,
  isNetworkError,
  isRecoverableSyncError,
  loadOfflineQueue,
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

const change = (key: ConfigChange['key'], value: unknown, expectedVersion: string): ConfigChange => ({
  key,
  value: value as never,
  expectedVersion,
  timestamp: 1,
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

  it('reads an unreadable stored queue as empty and clears on request', () => {
    localStorageMock.setItem('config-offline-queue', '{not json');
    expect(loadOfflineQueue()).toEqual([]);

    saveOfflineQueue([change('chatSettings', {}, '1000_0')]);
    clearOfflineQueue();
    expect(loadOfflineQueue()).toEqual([]);
  });
});

describe('offline failure classification', () => {
  it('treats fetch and network type errors, and backend-unavailable messages, as transient', () => {
    expect(isNetworkError(new TypeError('Failed to fetch'))).toBe(true);
    expect(isNetworkError(new Error('Failed to fetch'))).toBe(false);
    expect(isRecoverableSyncError('Backend not available')).toBe(true);
    expect(isRecoverableSyncError('You are OFFLINE')).toBe(true);
    expect(isRecoverableSyncError('Validation failed')).toBe(false);
  });
});
