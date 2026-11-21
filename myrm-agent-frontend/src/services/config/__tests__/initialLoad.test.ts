import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { landLateRecords, loadInitialConfigs } from '@/services/config/initialLoad';
import { ALL_CONFIG_KEYS, CORE_CONFIG_KEYS } from '@/services/config/types';
import type { ConfigAdapter, ConfigKey, ConfigRecord } from '@/services/config/types';

const fakeAdapter = (getAll: ReturnType<typeof vi.fn>) => ({ getAll }) as unknown as ConfigAdapter;
const loaded = new Map<ConfigKey, ConfigRecord>();

const record = (key: ConfigKey, value: unknown, version: string): ConfigRecord => ({
  key,
  value: value as never,
  meta: { version, updatedAt: '2026-01-01T00:00:00.000Z', deviceId: 'dev' },
});

describe('loadInitialConfigs', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('loads everything at once when not loading core-first', async () => {
    const getAll = vi.fn().mockResolvedValue(loaded);

    const result = await loadInitialConfigs(fakeAdapter(getAll), false);

    expect(getAll).toHaveBeenCalledWith();
    expect(result).toEqual({ configs: loaded, loadRemaining: null });
  });

  it('loads the core keys first and hands over a thunk for the rest, which is not started yet', async () => {
    const getAll = vi.fn().mockResolvedValue(loaded);

    const result = await loadInitialConfigs(fakeAdapter(getAll), true);

    expect(getAll).toHaveBeenCalledTimes(1);
    expect(getAll).toHaveBeenCalledWith(CORE_CONFIG_KEYS);

    await result.loadRemaining?.();

    expect(getAll).toHaveBeenCalledTimes(2);
    expect(getAll.mock.calls[1][0]).toEqual(ALL_CONFIG_KEYS.filter((key) => !CORE_CONFIG_KEYS.includes(key)));
  });

  it('retries the background load of the remaining keys like the first fetch', async () => {
    const getAll = vi
      .fn()
      .mockResolvedValueOnce(loaded)
      .mockRejectedValueOnce(new Error('down'))
      .mockResolvedValueOnce(loaded);

    const result = await loadInitialConfigs(fakeAdapter(getAll), true);
    const remaining = result.loadRemaining?.();
    await vi.advanceTimersByTimeAsync(500);

    await expect(remaining).resolves.toBe(loaded);
    expect(getAll).toHaveBeenCalledTimes(3);
  });

  it('retries a failing first fetch and succeeds on the third attempt', async () => {
    const getAll = vi
      .fn()
      .mockRejectedValueOnce(new Error('down'))
      .mockRejectedValueOnce(new Error('down'))
      .mockResolvedValueOnce(loaded);

    const pending = loadInitialConfigs(fakeAdapter(getAll), false);
    await vi.advanceTimersByTimeAsync(1000);

    await expect(pending).resolves.toEqual({ configs: loaded, loadRemaining: null });
    expect(getAll).toHaveBeenCalledTimes(3);
  });

  it('gives up with the last error after three failed attempts', async () => {
    const getAll = vi.fn().mockRejectedValue(new Error('still down'));

    const pending = loadInitialConfigs(fakeAdapter(getAll), false);
    const outcome = expect(pending).rejects.toThrow('still down');
    await vi.advanceTimersByTimeAsync(1000);

    await outcome;
    expect(getAll).toHaveBeenCalledTimes(3);
  });
});

describe('landLateRecords', () => {
  it('writes a late record into the cache and, as a copy, the base cache, and tells subscribers once', () => {
    const cache = new Map<ConfigKey, ConfigRecord>();
    const baseCache = new Map<ConfigKey, ConfigRecord>();
    const notify = vi.fn();
    const arrived = record('searchServices', { searchServiceConfigs: [] }, '1000_1');

    landLateRecords([['searchServices', arrived]], { cache, baseCache, notify });

    expect(cache.get('searchServices')).toBe(arrived);
    expect(baseCache.get('searchServices')).toEqual(arrived);
    expect(baseCache.get('searchServices')).not.toBe(arrived);
    expect(notify).toHaveBeenCalledTimes(1);
    expect(notify).toHaveBeenCalledWith('searchServices', arrived.value, arrived.meta);
  });

  it('keeps a key the cache already holds, because a late answer is older than what the cache has seen since', () => {
    const saved = record('searchServices', { searchServiceConfigs: ['saved'] }, '1000_2');
    const cache = new Map<ConfigKey, ConfigRecord>([['searchServices', saved]]);
    const baseCache = new Map<ConfigKey, ConfigRecord>();
    const notify = vi.fn();
    const securityConfig = record('securityConfig', {}, '1000_1');

    landLateRecords(
      [
        ['searchServices', record('searchServices', { searchServiceConfigs: ['stale'] }, '1000_1')],
        ['securityConfig', securityConfig],
      ],
      { cache, baseCache, notify },
    );

    expect(cache.get('searchServices')).toBe(saved);
    expect(baseCache.has('searchServices')).toBe(false);
    expect(cache.get('securityConfig')).toBe(securityConfig);
    expect(notify).toHaveBeenCalledTimes(1);
    expect(notify).toHaveBeenCalledWith('securityConfig', securityConfig.value, securityConfig.meta);
  });
});
