import { describe, expect, it, vi } from 'vitest';
import { resetConfigSyncManager, getConfigSyncManager } from '@/services/config/ConfigSyncManager';
import type { ConfigKey, SecurityConfigValue } from '@/services/config/types';

function seededManager(adapter: { get: ReturnType<typeof vi.fn> }) {
  resetConfigSyncManager();
  const manager = getConfigSyncManager();
  Object.assign(manager, {
    cache: new Map(),
    baseCache: new Map(),
    _isInitialized: true,
    adapter,
  });
  return manager;
}

function securityConfigValue(overrides: Partial<SecurityConfigValue> = {}): SecurityConfigValue {
  return {
    permissions: {},
    approvalTimeoutSeconds: 60,
    ...overrides,
  };
}

function record(key: ConfigKey, value: SecurityConfigValue) {
  return {
    key,
    value,
    meta: { version: '1000_0', updatedAt: '2026-01-01T00:00:00.000Z', deviceId: 'dev' },
  };
}

function yoloOf(manager: ReturnType<typeof getConfigSyncManager>): boolean {
  return (manager.get('securityConfig') as Partial<SecurityConfigValue> | null)?.yoloModeEnabled ?? false;
}

describe('ConfigSyncManager.ensureKeyLoaded', () => {
  it('returns immediately when the key is already cached', async () => {
    const adapter = { get: vi.fn() };
    const securityConfig = securityConfigValue({ yoloModeEnabled: true });
    const cache = new Map([['securityConfig', record('securityConfig', securityConfig)]]);
    const manager = seededManager(adapter);
    Object.assign(manager, { cache });

    await manager.ensureKeyLoaded('securityConfig');

    expect(adapter.get).not.toHaveBeenCalled();
    expect(yoloOf(manager)).toBe(true);
  });

  it('fetches and caches the key when not yet loaded', async () => {
    const securityConfig = securityConfigValue({ yoloModeEnabled: true });
    const adapter = {
      get: vi.fn().mockResolvedValue(record('securityConfig', securityConfig)),
    };
    const manager = seededManager(adapter);

    await manager.ensureKeyLoaded('securityConfig');

    expect(adapter.get).toHaveBeenCalledWith('securityConfig');
    expect(yoloOf(manager)).toBe(true);
  });

  it('does not throw when the adapter fetch fails (degraded to cached state)', async () => {
    const adapter = {
      get: vi.fn().mockRejectedValue(new Error('network down')),
    };
    const manager = seededManager(adapter);

    await expect(manager.ensureKeyLoaded('securityConfig')).resolves.toBeUndefined();
    expect(yoloOf(manager)).toBe(false);
  });
});
