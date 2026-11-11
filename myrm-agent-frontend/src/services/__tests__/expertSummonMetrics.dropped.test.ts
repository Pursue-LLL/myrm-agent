/**
 * Events that could not be sent are counted per surface, kept across reloads, and reported once the server answers
 * again. The server accepts at most 200 events per report and the browser keeps at most 1000 unreported ones.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const apiRequestMock = vi.hoisted(() => vi.fn());

vi.mock('@/lib/api', () => ({ apiRequest: apiRequestMock, ApiError: class ApiError extends Error {} }));

type Metrics = typeof import('@/services/expertSummonMetrics');

const STORAGE_KEY = 'expertSummonDroppedBufferV1';
const MAX_REPORT_COUNT = 200;

/** A fresh copy of the module: the unreported events are loaded from storage when it is first imported. */
async function loadMetrics(stored?: unknown): Promise<Metrics> {
  vi.resetModules();
  if (stored !== undefined) {
    localStorage.setItem(STORAGE_KEY, typeof stored === 'string' ? stored : JSON.stringify(stored));
  }
  return import('@/services/expertSummonMetrics');
}

const payloads = () => apiRequestMock.mock.calls.map(([, init]) => JSON.parse(String(init.body)));
const reports = () => payloads().filter((payload) => payload.event_type === 'dropped_report');
const reportedTotal = (surface: string) =>
  reports()
    .filter((report) => report.surface === surface)
    .reduce((sum, report) => sum + report.count, 0);

/** Fails the next `count` requests, then answers normally. */
function failNext(count: number) {
  for (let i = 0; i < count; i += 1) {
    apiRequestMock.mockRejectedValueOnce(new Error('offline'));
  }
}

describe('expertSummonMetrics dropped events', () => {
  beforeEach(() => {
    localStorage.clear();
    apiRequestMock.mockReset();
    apiRequestMock.mockResolvedValue({ accepted: true });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('reports what could not be sent with the next event that gets through, and only once', async () => {
    const metrics = await loadMetrics();
    failNext(1);

    metrics.recordExpertSummonSurfaceViewed('flow_pad_inline', 'first');
    metrics.recordExpertSummonSurfaceViewed('flow_pad_inline', 'second');
    metrics.recordExpertSummonSurfaceViewed('flow_pad_inline', 'third');
    await metrics.__flushExpertSummonMetricsForTest();

    expect(reports()).toEqual([
      expect.objectContaining({
        event_type: 'dropped_report',
        surface: 'flow_pad_inline',
        count: 1,
        context_key: 'second',
      }),
    ]);
    expect(localStorage.getItem(STORAGE_KEY)).toBeNull();
  });

  it('keeps a report the server did not take for the next time, without counting it as dropped again', async () => {
    const metrics = await loadMetrics();
    failNext(1);
    metrics.recordExpertSummonSurfaceViewed('flow_pad_inline');
    await metrics.__flushExpertSummonMetricsForTest();

    apiRequestMock.mockResolvedValueOnce({ accepted: true }).mockRejectedValueOnce(new Error('offline'));
    metrics.recordExpertSummonSurfaceViewed('flow_pad_inline');
    await metrics.__flushExpertSummonMetricsForTest();
    expect(JSON.parse(String(localStorage.getItem(STORAGE_KEY)))).toMatchObject({ flow_pad_inline: 1 });

    metrics.recordExpertSummonSurfaceViewed('flow_pad_inline');
    await metrics.__flushExpertSummonMetricsForTest();

    expect(reports().map((report) => report.count)).toEqual([1, 1]);
    expect(localStorage.getItem(STORAGE_KEY)).toBeNull();
  });

  it('counts each surface on its own and reports them one after another', async () => {
    const metrics = await loadMetrics();
    failNext(3);

    metrics.recordExpertSummonSurfaceViewed('mobile_hub_chip');
    metrics.recordExpertSummonSurfaceViewed('template_market');
    metrics.recordExpertSummonSurfaceViewed('template_market');
    metrics.recordExpertSummonSurfaceViewed('flow_pad_inline');
    await metrics.__flushExpertSummonMetricsForTest();

    expect(reports().map(({ surface, count }) => [surface, count])).toEqual([
      ['template_market', 2],
      ['mobile_hub_chip', 1],
    ]);
  });

  describe('a backlog larger than one report may carry', () => {
    it('is reported in parts the server accepts', async () => {
      const metrics = await loadMetrics({ flow_pad_inline: 450 });

      metrics.recordExpertSummonSurfaceViewed('flow_pad_inline');
      await metrics.__flushExpertSummonMetricsForTest();

      expect(reports().map((report) => report.count)).toEqual([MAX_REPORT_COUNT, MAX_REPORT_COUNT, 50]);
      expect(localStorage.getItem(STORAGE_KEY)).toBeNull();
    });

    it('keeps the parts not yet delivered when one is refused, and delivers them later', async () => {
      const metrics = await loadMetrics({ flow_pad_inline: 450 });
      apiRequestMock.mockResolvedValueOnce({ accepted: true }).mockResolvedValueOnce({ accepted: true });
      apiRequestMock.mockRejectedValueOnce(new Error('offline'));

      metrics.recordExpertSummonSurfaceViewed('flow_pad_inline');
      await metrics.__flushExpertSummonMetricsForTest();
      expect(JSON.parse(String(localStorage.getItem(STORAGE_KEY)))).toMatchObject({ flow_pad_inline: 250 });

      apiRequestMock.mockClear();
      metrics.recordExpertSummonSurfaceViewed('flow_pad_inline');
      await metrics.__flushExpertSummonMetricsForTest();

      expect(reportedTotal('flow_pad_inline')).toBe(250);
      expect(reports().every((report) => report.count <= MAX_REPORT_COUNT)).toBe(true);
    });
  });

  it('stops counting once a thousand events wait to be reported', async () => {
    const metrics = await loadMetrics({ template_market: 1000 });
    failNext(1);

    metrics.recordExpertSummonSurfaceViewed('flow_pad_inline');
    metrics.recordExpertSummonSurfaceViewed('flow_pad_inline');
    await metrics.__flushExpertSummonMetricsForTest();

    expect(reportedTotal('template_market')).toBe(1000);
    expect(reportedTotal('flow_pad_inline')).toBe(0);
  });

  describe('across page loads', () => {
    it('writes the unreported events to storage and picks them up when the module loads again', async () => {
      const before = await loadMetrics();
      failNext(2);
      before.recordExpertSummonSurfaceViewed('flow_pad_inline');
      before.recordExpertSummonSurfaceViewed('flow_pad_inline');
      await before.__flushExpertSummonMetricsForTest();
      expect(JSON.parse(String(localStorage.getItem(STORAGE_KEY)))).toMatchObject({ flow_pad_inline: 2 });

      const after = await loadMetrics();
      after.recordExpertSummonSurfaceViewed('template_market');
      await after.__flushExpertSummonMetricsForTest();

      expect(reportedTotal('flow_pad_inline')).toBe(2);
      expect(localStorage.getItem(STORAGE_KEY)).toBeNull();
    });

    it('trusts only sane counts from storage', async () => {
      const metrics = await loadMetrics({
        template_market: 5,
        flow_pad_inline: 5000,
        mobile_hub_chip: -2,
        message_input_plus: 'many',
        empty_chat_featured: 7.9,
      });

      metrics.recordExpertSummonSurfaceViewed('template_market');
      await metrics.__flushExpertSummonMetricsForTest();

      expect(reportedTotal('template_market')).toBe(5);
      expect(reportedTotal('flow_pad_inline')).toBe(1000);
      expect(reportedTotal('empty_chat_featured')).toBe(7);
      expect(reportedTotal('mobile_hub_chip')).toBe(0);
      expect(reportedTotal('message_input_plus')).toBe(0);
    });

    it('starts empty when what storage holds cannot be read', async () => {
      const metrics = await loadMetrics('{not json');

      metrics.recordExpertSummonSurfaceViewed('template_market');
      await metrics.__flushExpertSummonMetricsForTest();

      expect(reports()).toEqual([]);
    });

    it('still reports within the session when storage refuses to keep anything', async () => {
      const refuse = () => {
        throw new DOMException('quota', 'QuotaExceededError');
      };
      vi.stubGlobal('localStorage', { getItem: () => null, setItem: refuse, removeItem: refuse });
      const metrics = await loadMetrics();
      failNext(1);

      metrics.recordExpertSummonSurfaceViewed('flow_pad_inline');
      metrics.recordExpertSummonSurfaceViewed('flow_pad_inline');
      await metrics.__flushExpertSummonMetricsForTest();

      expect(reportedTotal('flow_pad_inline')).toBe(1);
    });
  });
});
