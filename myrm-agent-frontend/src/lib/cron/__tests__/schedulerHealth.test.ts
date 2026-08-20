import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import {
  fetchSchedulerHealthOnce,
  getCachedSchedulerHealth,
  resetSchedulerHealthForTests,
  subscribeSchedulerHealth,
} from '../schedulerHealth';

vi.mock('@/lib/api', () => ({
  apiRequest: vi.fn(),
}));

vi.mock('@/lib/backend-health', () => ({
  checkBackendReadyOnce: vi.fn(() => Promise.resolve(true)),
}));

describe('schedulerHealth', () => {
  beforeEach(() => {
    resetSchedulerHealthForTests();
    vi.clearAllMocks();
  });

  afterEach(() => {
    resetSchedulerHealthForTests();
  });

  it('dedupes concurrent fetches via single-flight', async () => {
    const { apiRequest } = await import('@/lib/api');
    vi.mocked(apiRequest).mockImplementation(
      () =>
        new Promise((resolve) => {
          setTimeout(
            () =>
              resolve({
                status: 'green',
                running: true,
                last_tick_at: '2026-06-17T08:00:00Z',
                tick_errors: 0,
                last_tick_age_seconds: 1,
                has_timer: true,
              }),
            10,
          );
        }),
    );

    const [first, second] = await Promise.all([fetchSchedulerHealthOnce(), fetchSchedulerHealthOnce()]);

    expect(first).toEqual(second);
    expect(apiRequest).toHaveBeenCalledTimes(1);
  });

  it('skips fetch when backend is not ready', async () => {
    const { checkBackendReadyOnce } = await import('@/lib/backend-health');
    const { apiRequest } = await import('@/lib/api');
    vi.mocked(checkBackendReadyOnce).mockResolvedValueOnce(false);

    const result = await fetchSchedulerHealthOnce();

    expect(result).toBeNull();
    expect(apiRequest).not.toHaveBeenCalled();
  });

  it('notifies subscribers and shares cached health', async () => {
    const { apiRequest } = await import('@/lib/api');
    vi.mocked(apiRequest).mockResolvedValueOnce({
      status: 'yellow',
      running: true,
      last_tick_at: '2026-06-17T08:00:00Z',
      tick_errors: 2,
      last_tick_age_seconds: 120,
      has_timer: true,
    });

    const listener = vi.fn();
    const unsubscribe = subscribeSchedulerHealth(listener);

    await fetchSchedulerHealthOnce();

    expect(listener).toHaveBeenCalled();
    expect(getCachedSchedulerHealth()?.status).toBe('yellow');
    unsubscribe();
  });
});
