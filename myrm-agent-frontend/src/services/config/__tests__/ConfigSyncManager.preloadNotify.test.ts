import { beforeEach, describe, expect, it, vi } from 'vitest';
import { resetConfigSyncManager, getConfigSyncManager } from '@/services/config/ConfigSyncManager';

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

const CORE_KEYS = ['providers', 'chatSettings', 'personalSettings'];

function configRecord(key: string, value: unknown) {
  return {
    key,
    value,
    meta: { version: '1000_0', updatedAt: '2026-01-01T00:00:00.000Z', deviceId: 'dev' },
    encrypted: false,
  };
}

function configsResponse(entries: Array<[string, unknown]>) {
  return {
    configs: Object.fromEntries(entries.map(([key, value]) => [key, configRecord(key, value)])),
  };
}

const nonCoreEntries: Array<[string, unknown]> = [
  ['securityConfig', { yoloModeEnabled: true, permissions: {}, approvalTimeoutSeconds: 60 }],
  ['chatSettings', {}],
  ['personalSettings', {}],
];

describe('ConfigSyncManager progressive preload notifies listeners', () => {
  beforeEach(() => {
    resetConfigSyncManager();
    vi.restoreAllMocks();
  });

  it('fires subscribe callbacks once background-preloaded keys land in the cache', async () => {
    const coreResponse = configsResponse([
      ['providers', { providers: [] }],
      ['chatSettings', {}],
      ['personalSettings', {}],
    ]);
    const restResponse = configsResponse(nonCoreEntries);

    const mockFetch = vi.fn((url: RequestInfo | URL) => {
      const path = String(url);
      if (CORE_KEYS.every((k) => path.includes(encodeURIComponent(k)))) {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: () => Promise.resolve(coreResponse),
        } as Response);
      }
      return Promise.resolve({
        ok: true,
        status: 200,
        json: () => Promise.resolve(restResponse),
      } as Response);
    });
    global.fetch = mockFetch as unknown as typeof fetch;

    const manager = getConfigSyncManager();
    const listener = vi.fn();
    manager.subscribe('securityConfig', listener);

    await manager.initialize();
    expect(mockFetch).toHaveBeenCalled();

    // 等待后台预加载（fire-and-forget promise）落地
    await new Promise((resolve) => setTimeout(resolve, 25));

    expect(manager.get('securityConfig')).not.toBeNull();
    expect(listener).toHaveBeenCalled();
    expect(listener.mock.calls[0]?.[0]).toBe('securityConfig');
    expect(manager.get('securityConfig')).toEqual(expect.objectContaining({ yoloModeEnabled: true }));
  });
});
