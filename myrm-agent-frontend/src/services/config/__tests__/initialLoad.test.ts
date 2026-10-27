import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { loadInitialConfigs } from '@/services/config/initialLoad';
import { ALL_CONFIG_KEYS, CORE_CONFIG_KEYS } from '@/services/config/types';
import type { ConfigAdapter, ConfigKey, ConfigRecord } from '@/services/config/types';

const fakeAdapter = (getAll: ReturnType<typeof vi.fn>) => ({ getAll }) as unknown as ConfigAdapter;
const loaded = new Map<ConfigKey, ConfigRecord>();

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
