import { afterEach, describe, expect, it, vi } from 'vitest';
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
  afterEach(() => {
    vi.clearAllTimers();
    vi.useRealTimers();
  });

  it('reports a cached key as known without asking the adapter', async () => {
    const adapter = { get: vi.fn() };
    const securityConfig = securityConfigValue({ yoloModeEnabled: true });
    const cache = new Map([['securityConfig', record('securityConfig', securityConfig)]]);
    const manager = seededManager(adapter);
    Object.assign(manager, { cache });

    await expect(manager.ensureKeyLoaded('securityConfig')).resolves.toBe(true);

    expect(adapter.get).not.toHaveBeenCalled();
    expect(yoloOf(manager)).toBe(true);
  });

  it('fetches and caches the key when not yet loaded', async () => {
    const securityConfig = securityConfigValue({ yoloModeEnabled: true });
    const adapter = {
      get: vi.fn().mockResolvedValue(record('securityConfig', securityConfig)),
    };
    const manager = seededManager(adapter);

    await expect(manager.ensureKeyLoaded('securityConfig')).resolves.toBe(true);

    expect(adapter.get).toHaveBeenCalledWith('securityConfig');
    expect(yoloOf(manager)).toBe(true);
  });

  it('reports a key the server does not have as known, and leaves it out of the cache', async () => {
    const adapter = { get: vi.fn().mockResolvedValue(null) };
    const manager = seededManager(adapter);

    await expect(manager.ensureKeyLoaded('securityConfig')).resolves.toBe(true);

    expect(manager.getRecord('securityConfig')).toBeNull();
  });

  it('reports the key as unknown instead of throwing when the adapter fetch fails (degraded to cached state)', async () => {
    const adapter = {
      get: vi.fn().mockRejectedValue(new Error('network down')),
    };
    const manager = seededManager(adapter);

    await expect(manager.ensureKeyLoaded('securityConfig')).resolves.toBe(false);
    expect(yoloOf(manager)).toBe(false);
  });

  it('keeps what the user saved while the read was in flight, and does not announce the older answer', async () => {
    vi.useFakeTimers();
    const savedServices = { searchServiceConfigs: [{ id: 'saved' }] };
    let answer: (found: ReturnType<typeof record>) => void = () => {};
    const pendingAnswer = new Promise<ReturnType<typeof record>>((resolve) => {
      answer = resolve;
    });
    const adapter = { get: vi.fn().mockReturnValue(pendingAnswer), getDeviceId: () => 'dev' };
    const manager = seededManager(adapter);
    const listener = vi.fn();
    manager.subscribe('searchServices', listener);

    const loading = manager.ensureKeyLoaded('searchServices');
    await vi.advanceTimersByTimeAsync(0);
    expect(adapter.get).toHaveBeenCalledTimes(1);
    manager.set('searchServices', savedServices as never);
    listener.mockClear();
    answer(record('searchServices', { searchServiceConfigs: [{ id: 'older' }] } as never));

    await expect(loading).resolves.toBe(true);
    expect(manager.get('searchServices')).toEqual(savedServices);
    expect(listener).not.toHaveBeenCalled();
  });
});
