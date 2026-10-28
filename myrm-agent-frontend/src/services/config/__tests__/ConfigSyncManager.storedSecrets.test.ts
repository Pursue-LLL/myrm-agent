/**
 * Offline-queue entries for non-allowlisted keys (secrets included) that already sit in `localStorage` must leave
 * browser storage as soon as the manager starts — also while the backend stays unreachable — yet still be replayed
 * from memory once it is back.
 */

import { describe, expect, it, beforeEach, afterEach, vi } from 'vitest';
import { ensureLocalBackendReady } from '@/lib/backend-health';
import { ConfigSyncManager, resetConfigSyncManager } from '@/services/config/ConfigSyncManager';

vi.mock('@/lib/deploy-mode', () => ({
  isLocalMode: vi.fn(() => true),
  getApiBaseUrl: vi.fn(() => 'http://localhost:8080/api/v1'),
}));

vi.mock('@/lib/backend-health', () => ({
  ensureLocalBackendReady: vi.fn(() => Promise.resolve(true)),
  markLocalBackendUnreachable: vi.fn(),
}));

vi.mock('@/lib/platform-readiness', () => ({
  ensurePlatformReadiness: vi.fn(() => Promise.resolve({ state: 'ready', database: false })),
  whenDatabaseReady: vi.fn(() => Promise.resolve(true)),
}));

const mockFetch = vi.fn();
global.fetch = mockFetch;

const OFFLINE_QUEUE_KEY = 'config-offline-queue';
const SECRET = 'sk-queue-sentinel-91c2';

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

const storedSecretEntry = { key: 'privacyRoutingSecret', value: { localApiKey: SECRET }, expectedVersion: '1000_0' };
const chatSettingsEntry = { key: 'chatSettings', value: { customModelInfo: {} }, expectedVersion: '1000_0' };

/** Puts a queue straight into storage, then forgets the seeding calls. */
const seedQueue = (entries: object[]) => {
  localStorageMock.setItem(OFFLINE_QUEUE_KEY, JSON.stringify(entries.map((entry) => ({ ...entry, timestamp: 1 }))));
  localStorageMock.setItem.mockClear();
};

const queuedKeys = () => {
  const stored = localStorageMock.getItem(OFFLINE_QUEUE_KEY);
  return stored ? (JSON.parse(stored) as { key: string }[]).map((change) => change.key) : [];
};

describe('ConfigSyncManager non-allowlisted entries already in storage', () => {
  let manager: ConfigSyncManager;

  beforeEach(() => {
    vi.clearAllMocks();
    localStorageMock.clear();
    resetConfigSyncManager();
    manager = new ConfigSyncManager();
  });

  afterEach(() => {
    resetConfigSyncManager();
  });

  it('removes the secret entry from browser storage while the backend is unreachable and keeps the allowlisted one', async () => {
    vi.mocked(ensureLocalBackendReady).mockResolvedValueOnce(false);
    seedQueue([storedSecretEntry, chatSettingsEntry]);

    await manager.initialize();

    expect(manager.status).toBe('offline');
    expect(mockFetch).not.toHaveBeenCalled();
    expect(queuedKeys()).toEqual(['chatSettings']);
    expect(String(localStorageMock.getItem(OFFLINE_QUEUE_KEY))).not.toContain(SECRET);
    expect(localStorageMock.setItem.mock.calls.map(([, value]) => String(value)).join('\n')).not.toContain(SECRET);
  });

  it('empties the storage key when nothing allowlisted was queued', async () => {
    vi.mocked(ensureLocalBackendReady).mockResolvedValueOnce(false);
    seedQueue([storedSecretEntry]);

    await manager.initialize();

    expect(localStorageMock.getItem(OFFLINE_QUEUE_KEY)).toBeNull();
  });

  it('leaves a queue of allowlisted keys exactly as it was', async () => {
    vi.mocked(ensureLocalBackendReady).mockResolvedValueOnce(false);
    seedQueue([chatSettingsEntry]);
    const before = localStorageMock.getItem(OFFLINE_QUEUE_KEY);

    await manager.initialize();

    expect(localStorageMock.getItem(OFFLINE_QUEUE_KEY)).toBe(before);
    expect(localStorageMock.setItem).not.toHaveBeenCalled();
    expect(localStorageMock.removeItem).not.toHaveBeenCalled();
  });

  it('is gone from storage before the first config request, yet still replays the secret from memory', async () => {
    seedQueue([storedSecretEntry]);
    let queueWhenConfigsWereRequested: string | null = 'not requested';
    mockFetch.mockImplementationOnce(() => {
      queueWhenConfigsWereRequested = localStorageMock.getItem(OFFLINE_QUEUE_KEY);
      return Promise.resolve({
        ok: true,
        json: () =>
          Promise.resolve({
            configs: {
              privacyRoutingSecret: {
                key: 'privacyRoutingSecret',
                value: { localApiKey: 'stored-value' },
                version: '1000_0',
                updatedAt: '2026-01-01T00:00:00.000Z',
                deviceId: 'tauri-local',
              },
            },
          }),
      });
    });
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({ success: true, conflicts: [], newVersions: { privacyRoutingSecret: '1000_1' } }),
    });

    await manager.initialize();

    expect(queueWhenConfigsWereRequested).toBeNull();
    const syncRequest = mockFetch.mock.calls[1]?.[1] as RequestInit | undefined;
    expect(String(syncRequest?.body)).toContain(SECRET);
    expect(localStorageMock.setItem.mock.calls.map(([, value]) => String(value)).join('\n')).not.toContain(SECRET);
    expect(localStorageMock.getItem(OFFLINE_QUEUE_KEY)).toBeNull();
  });
});
