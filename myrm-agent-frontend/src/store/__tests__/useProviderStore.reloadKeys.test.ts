/**
 * The migration import writes the model slots and imported API keys straight into the backend's providers row. With
 * the real config manager and the real provider store, a reload of that row must put the keys on the settings page,
 * and the user's next edit must go out on the backend's version with those keys still in the saved bundle, instead of
 * a stale bundle that would drop them.
 */

import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/services/provider-oauth', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/services/provider-oauth')>()),
  fetchProviderOAuthStatus: vi.fn(async () => ({ provider: 'openai', issuer: 'openai', connected: false })),
}));
vi.mock('@/lib/backend-health', () => ({ ensureLocalBackendReady: vi.fn(async () => {}) }));
vi.mock('@/lib/deploy-mode', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/deploy-mode')>()),
  isLocalMode: () => false,
}));
vi.mock('@/lib/platform-readiness', () => ({
  ensurePlatformReadiness: vi.fn(async () => ({ database: false })),
}));

import { getConfigSyncManager, resetConfigSyncManager } from '@/services/config/ConfigSyncManager';
import type { ConfigRecord, ProvidersConfigValue, SyncResult } from '@/services/config/types';
import { getInitialDefaultModelConfig, getInitialProviders } from '../config/providerTypes';
import useProviderStore from '../useProviderStore';

const DEVICE = 'dev-local';
const IMPORTED_KEY = 'sk-imported';

const providersWithKeys = (keys: string[]): ProvidersConfigValue => ({
  providers: getInitialProviders().map((provider) =>
    provider.id === 'openai'
      ? {
          ...provider,
          isEnabled: true,
          apiKeys: keys.map((key, index) => ({ id: `key-${index}`, key, remark: '', isActive: true })),
        }
      : provider,
  ),
  defaultModelConfig: getInitialDefaultModelConfig(),
  customModelInfo: {},
});

const providersRecord = (value: ProvidersConfigValue, version: string): ConfigRecord => ({
  key: 'providers',
  value,
  meta: { version, updatedAt: '2026-01-01T00:00:00.000Z', deviceId: DEVICE },
});

const openaiKeys = (value: ProvidersConfigValue): string[] =>
  value.providers.find((provider) => provider.id === 'openai')?.apiKeys.map((apiKey) => apiKey.key) ?? [];

const accepted: SyncResult = { success: true, conflicts: [], newVersions: new Map([['providers', '1000_6']]) };

describe('provider settings after the backend stored imported keys', () => {
  beforeEach(() => {
    resetConfigSyncManager();
  });

  it('shows the imported key, and the next edit keeps it and goes out on the backend version', async () => {
    const sync = vi.fn().mockResolvedValue(accepted);
    const getAll = vi
      .fn()
      .mockResolvedValue(new Map([['providers', providersRecord(providersWithKeys([IMPORTED_KEY]), '1000_5')]]));
    const manager = getConfigSyncManager();
    Object.assign(manager, {
      adapter: { getDeviceId: () => DEVICE, sync, getAll },
      cache: new Map([['providers', providersRecord(providersWithKeys([]), '1000_0')]]),
      baseCache: new Map([['providers', providersRecord(providersWithKeys([]), '1000_0')]]),
      _isInitialized: true,
    });
    await useProviderStore.getState().retryInit();
    expect(openaiKeys(useProviderStore.getState())).toEqual([]);

    await manager.reloadKeys(['providers']);

    expect(openaiKeys(useProviderStore.getState())).toEqual([IMPORTED_KEY]);

    useProviderStore.getState().setProviderEnabled('openai', false);
    await manager.forceSync();

    expect(sync).toHaveBeenCalledOnce();
    const [sent] = sync.mock.calls[0] as [{ key: string; expectedVersion: string; value: ProvidersConfigValue }[]];
    expect(sent).toHaveLength(1);
    expect(sent[0]).toMatchObject({ key: 'providers', expectedVersion: '1000_5' });
    expect(openaiKeys(sent[0].value)).toEqual([IMPORTED_KEY]);
  });
});
