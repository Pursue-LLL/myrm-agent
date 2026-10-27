import { describe, expect, it, beforeEach, afterEach, vi } from 'vitest';
import { ConfigSyncManager, resetConfigSyncManager } from '@/services/config/ConfigSyncManager';
import { OFFLINE_PERSISTABLE_CONFIG_KEYS } from '@/services/config/offlinePersistableKeys';
import { ALL_CONFIG_KEYS, DEFAULT_PERSONAL_SETTINGS } from '@/services/config/types';

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
const SECRET = 'sk-local-model-offline-sentinel-7f3a';

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

const backendUnavailable = () => ({ ok: false, status: 503, statusText: 'Service Unavailable' });
const syncOk = (newVersions: Record<string, string>) => ({
  ok: true,
  json: () => Promise.resolve({ success: true, conflicts: [], newVersions }),
});

/** Everything the manager ever wrote to browser storage, whether or not it was removed again. */
const everythingWritten = () => localStorageMock.setItem.mock.calls.map(([, value]) => String(value)).join('\n');

const queuedKeys = () => {
  const stored = localStorageMock.getItem(OFFLINE_QUEUE_KEY);
  return stored ? (JSON.parse(stored) as { key: string }[]).map((change) => change.key) : [];
};

describe('ConfigSyncManager offline queue keeps secrets out of browser storage', () => {
  let manager: ConfigSyncManager;

  beforeEach(async () => {
    vi.clearAllMocks();
    localStorageMock.clear();
    resetConfigSyncManager();
    manager = new ConfigSyncManager();
    mockFetch.mockResolvedValueOnce({ ok: true, json: () => Promise.resolve({ configs: {} }) });
    await manager.initialize();
  });

  afterEach(() => {
    resetConfigSyncManager();
  });

  it('never writes a sealed key change to localStorage while the backend is down, yet still retries it from memory', async () => {
    mockFetch.mockResolvedValueOnce(backendUnavailable());
    manager.set('privacyRoutingSecret', { localApiKey: SECRET });

    const failed = await manager.forceSync();

    expect(failed.success).toBe(false);
    expect(manager.status).toBe('offline');
    expect(everythingWritten()).not.toContain(SECRET);
    expect(localStorageMock.setItem).not.toHaveBeenCalledWith(OFFLINE_QUEUE_KEY, expect.anything());

    mockFetch.mockResolvedValueOnce(syncOk({ privacyRoutingSecret: '1000_1' }));
    const retried = await manager.forceSync();

    expect(retried.success).toBe(true);
    const retryBody = String((mockFetch.mock.calls.at(-1)?.[1] as RequestInit).body);
    expect(retryBody).toContain(SECRET);
  });

  it('still persists a non-sensitive change for replay after a reload', async () => {
    mockFetch.mockResolvedValueOnce(backendUnavailable());

    manager.set('chatSettings', { ...(manager.get('chatSettings') ?? {}), marker: 'offline-edit' } as never);
    await manager.forceSync();

    expect(queuedKeys()).toEqual(['chatSettings']);
  });

  it('persists the non-sensitive part of a mixed queue and leaves the secret out when a fast-path flush saves the queue', async () => {
    mockFetch.mockResolvedValueOnce(syncOk({ privacyRoutingSecret: '1000_1', personalSettings: '1000_1' }));

    manager.set('privacyRoutingSecret', { localApiKey: SECRET });
    manager.set('personalSettings', { ...DEFAULT_PERSONAL_SETTINGS, activeThemeProfileId: 'ocean-blue' });
    await vi.waitFor(() => expect(mockFetch.mock.calls.length).toBeGreaterThanOrEqual(2));

    const savedQueue = localStorageMock.setItem.mock.calls.find(([key]) => key === OFFLINE_QUEUE_KEY);
    expect(savedQueue).toBeDefined();
    expect(JSON.parse(String(savedQueue?.[1])).map((change: { key: string }) => change.key)).toEqual([
      'personalSettings',
    ]);
    expect(everythingWritten()).not.toContain(SECRET);
    expect(String((mockFetch.mock.calls.at(-1)?.[1] as RequestInit).body)).toContain(SECRET);
  });

  it('only allowlists keys that exist', () => {
    for (const key of OFFLINE_PERSISTABLE_CONFIG_KEYS) {
      expect(ALL_CONFIG_KEYS).toContain(key);
    }
    expect(OFFLINE_PERSISTABLE_CONFIG_KEYS.has('privacyRoutingSecret')).toBe(false);
    expect(OFFLINE_PERSISTABLE_CONFIG_KEYS.has('providers')).toBe(false);
  });
});
