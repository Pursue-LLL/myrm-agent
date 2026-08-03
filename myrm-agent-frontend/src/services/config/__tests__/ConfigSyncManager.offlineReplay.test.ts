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

describe('ConfigSyncManager offline replay hydrate', () => {
  let manager: ConfigSyncManager;

  const createSettings = (overrides?: Partial<PersonalSettingsConfigValue>): PersonalSettingsConfigValue => ({
    ...DEFAULT_PERSONAL_SETTINGS,
    ...overrides,
  });

  const buildServerConfigsResponse = (personalSettings: PersonalSettingsConfigValue) => ({
    configs: {
      personalSettings: {
        key: 'personalSettings',
        value: personalSettings,
        version: '1000_0',
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

  it('hydrates cache from offline queue when server personalSettings is stale', async () => {
    const stale = createSettings({ activeThemeProfileId: 'official-default' });
    const pending = createSettings({ activeThemeProfileId: 'ocean-blue' });

    localStorageMock.setItem(
      OFFLINE_QUEUE_KEY,
      JSON.stringify([
        {
          key: 'personalSettings',
          value: pending,
          expectedVersion: '1000_0',
          timestamp: Date.now(),
        },
      ]),
    );

    mockFetch
      .mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve(buildServerConfigsResponse(stale)),
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

    const hydrated = manager.get('personalSettings');
    expect(hydrated?.activeThemeProfileId).toBe('ocean-blue');
    expect(localStorageMock.getItem(OFFLINE_QUEUE_KEY)).toBeNull();
  });

  it('keeps synced value in cache after flushSync success without prior optimistic set', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({ configs: {} }),
    });
    await manager.initialize();

    const pending = createSettings({ activeThemeProfileId: 'forest-green' });

    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () =>
        Promise.resolve({
          success: true,
          conflicts: [],
          newVersions: { personalSettings: '1000_1' },
        }),
    });

    Object.assign(manager, {
      changeQueue: [
        {
          key: 'personalSettings',
          value: pending,
          expectedVersion: '1000_0',
          timestamp: Date.now(),
        },
      ],
    });

    await manager.forceSync();

    const hydrated = manager.get('personalSettings');
    expect(hydrated?.activeThemeProfileId).toBe('forest-green');
  });
});
