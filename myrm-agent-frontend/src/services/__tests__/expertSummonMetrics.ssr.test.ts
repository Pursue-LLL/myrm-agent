/**
 * Pages are rendered on the server first, where there is no window: the metrics client must load, count what it
 * cannot send in memory, and reset without touching storage.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const apiRequestMock = vi.hoisted(() => vi.fn());

vi.mock('@/lib/api', () => ({ apiRequest: apiRequestMock, ApiError: class ApiError extends Error {} }));

/** A copy of the module that is evaluated while `window` does not exist, as it is on the server. */
async function loadOnTheServer() {
  vi.stubGlobal('window', undefined);
  vi.resetModules();
  return import('@/services/expertSummonMetrics');
}

describe('expertSummonMetrics without a window', () => {
  beforeEach(() => {
    apiRequestMock.mockReset();
    apiRequestMock.mockResolvedValue({ accepted: true });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('keeps what it could not send in memory and reports it with the next event that gets through', async () => {
    const metrics = await loadOnTheServer();
    expect(typeof window).toBe('undefined');
    apiRequestMock.mockRejectedValueOnce(new Error('offline'));

    metrics.recordExpertSummonSurfaceViewed('flow_pad_inline');
    metrics.recordExpertSummonSurfaceViewed('flow_pad_inline');
    await metrics.__flushExpertSummonMetricsForTest();

    const reports = apiRequestMock.mock.calls
      .map(([, init]) => JSON.parse(String(init.body)))
      .filter((payload) => payload.event_type === 'dropped_report');
    expect(reports).toEqual([expect.objectContaining({ surface: 'flow_pad_inline', count: 1 })]);
  });

  it('can be reset without a window', async () => {
    const metrics = await loadOnTheServer();

    expect(() => metrics.__resetExpertSummonMetricsForTest()).not.toThrow();
  });
});
