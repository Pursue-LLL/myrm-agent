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

describe('ConfigSyncManager theme fast-path sync', () => {
  let manager: ConfigSyncManager;

  const createSettings = (overrides?: Partial<PersonalSettingsConfigValue>): PersonalSettingsConfigValue => ({
    ...DEFAULT_PERSONAL_SETTINGS,
    ...overrides,
  });

  beforeEach(async () => {
    vi.clearAllMocks();
    localStorageMock.clear();
    resetConfigSyncManager();
    manager = new ConfigSyncManager();
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({ configs: {} }),
    });
    await manager.initialize();
  });

  afterEach(() => {
    resetConfigSyncManager();
  });

  it('flushes theme changes immediately and persists offline queue before debounce', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () =>
        Promise.resolve({
          success: true,
          conflicts: [],
          newVersions: { personalSettings: '1706000000000_1' },
        }),
    });

    const next = createSettings({ activeThemeProfileId: 'ocean-blue' });
    manager.set('personalSettings', next);

    await vi.waitFor(() => {
      expect(mockFetch).toHaveBeenCalledTimes(2);
    });

    const stored = localStorageMock.getItem(OFFLINE_QUEUE_KEY);
    expect(stored === null || stored === '[]').toBe(true);
  });

  it('keeps debounced sync for non-theme personalSettings changes', async () => {
    vi.useFakeTimers();

    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () =>
        Promise.resolve({
          success: true,
          conflicts: [],
          newVersions: { personalSettings: '1706000000000_1' },
        }),
    });

    manager.set('personalSettings', createSettings({ systemInstructions: 'hello' }));
    expect(mockFetch).toHaveBeenCalledTimes(1);

    await vi.advanceTimersByTimeAsync(1100);
    expect(mockFetch).toHaveBeenCalledTimes(2);

    vi.useRealTimers();
  });

  it('persists theme change to offline queue before flush completes', async () => {
    let resolveSync: ((value: unknown) => void) | undefined;
    mockFetch.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          resolveSync = resolve;
        }),
    );

    manager.set('personalSettings', createSettings({ activeThemeProfileId: 'forest-green' }));

    await vi.waitFor(() => {
      expect(localStorageMock.setItem).toHaveBeenCalled();
    });

    const stored = localStorageMock.getItem(OFFLINE_QUEUE_KEY);
    expect(stored).toBeTruthy();
    const parsed = JSON.parse(stored!) as Array<{ key: string; value: PersonalSettingsConfigValue }>;
    expect(parsed[0]?.key).toBe('personalSettings');
    expect(parsed[0]?.value.activeThemeProfileId).toBe('forest-green');

    resolveSync?.({
      ok: true,
      json: () =>
        Promise.resolve({
          success: true,
          conflicts: [],
          newVersions: { personalSettings: '1706000000000_1' },
        }),
    });

    await vi.waitFor(() => {
      expect(mockFetch).toHaveBeenCalledTimes(2);
    });
  });
});
