import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { apiRequest } from '@/lib/api';
import {
  __flushWikiEvidenceMetricsForTest,
  __resetWikiEvidenceMetricsForTest,
  getWikiEvidenceSummary,
  recordEvidenceSurface,
  recordSnippetClose,
  recordSnippetOpen,
  recordWikiQuery,
} from '@/services/wikiEvidenceMetrics';

vi.mock('@/lib/api', () => ({
  apiRequest: vi.fn(),
}));

const apiRequestMock = vi.mocked(apiRequest);

describe('wikiEvidenceMetrics', () => {
  beforeEach(() => {
    apiRequestMock.mockReset();
    apiRequestMock.mockResolvedValue({ accepted: true });
    __resetWikiEvidenceMetricsForTest();
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-07-27T08:00:00.000Z'));
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('posts evidence surface count with silent mode', async () => {
    recordEvidenceSurface('settings', 3);
    await __flushWikiEvidenceMetricsForTest();

    expect(apiRequestMock).toHaveBeenCalledWith('/statistics/wiki-evidence/events', {
      method: 'POST',
      body: JSON.stringify({
        event_type: 'evidence_surface',
        surface: 'settings',
        context_key: 'global',
        count: 3,
      }),
      silent: true,
    });
  });

  it('marks only first query after evidence interaction as requery', async () => {
    recordSnippetOpen('chat', 'L1');
    vi.advanceTimersByTime(2500);
    recordSnippetClose('chat', 2500);

    recordWikiQuery('settings');
    recordWikiQuery('settings');
    await __flushWikiEvidenceMetricsForTest();

    const firstQueryCall = apiRequestMock.mock.calls[2];
    const secondQueryCall = apiRequestMock.mock.calls[3];
    expect(firstQueryCall).toBeDefined();
    expect(secondQueryCall).toBeDefined();

    const firstPayload = JSON.parse(String(firstQueryCall?.[1]?.body));
    const secondPayload = JSON.parse(String(secondQueryCall?.[1]?.body));

    expect(firstPayload.after_evidence).toBe(true);
    expect(secondPayload.after_evidence).toBe(false);
  });

  it('flushes dropped events after next successful post', async () => {
    apiRequestMock.mockRejectedValueOnce(new Error('offline'));
    apiRequestMock.mockResolvedValue({ accepted: true });

    recordSnippetOpen('chat', 'L1', 'agent:test');
    await __flushWikiEvidenceMetricsForTest();
    recordWikiQuery('chat', 'agent:test');
    await __flushWikiEvidenceMetricsForTest();

    const queryPayload = JSON.parse(String(apiRequestMock.mock.calls[1]?.[1]?.body));
    const droppedPayload = JSON.parse(String(apiRequestMock.mock.calls[2]?.[1]?.body));

    expect(queryPayload.event_type).toBe('query_submitted');
    expect(queryPayload.context_key).toBe('agent:test');
    expect(droppedPayload.event_type).toBe('dropped_report');
    expect(droppedPayload.surface).toBe('chat');
    expect(droppedPayload.count).toBe(1);
    expect(droppedPayload.context_key).toBe('agent:test');
  });

  it('fetches wiki evidence summary from statistics API', async () => {
    apiRequestMock.mockResolvedValueOnce({
      days: 30,
      retention_days: 90,
      total_events: 10,
      evidence_surface_count: 4,
      snippet_open_count: 2,
      dropped_event_count: 0,
      snippet_expansion_rate: 0.5,
      deep_verification_count: 1,
      deep_verification_rate: 0.5,
      quick_bounce_count: 0,
      quick_bounce_rate: 0,
      query_count: 2,
      requery_count: 1,
      requery_rate: 0.5,
      verification_dwell_avg_ms: 1234,
      verification_dwell_sample_count: 2,
      snippet_open_by_surface: { chat: 1, settings: 1 },
      snippet_open_by_level: { L0: 0, L1: 1, L2: 1 },
    });

    const result = await getWikiEvidenceSummary();

    expect(apiRequestMock).toHaveBeenCalledWith('/statistics/wiki-evidence/summary?days=30');
    expect(result.requery_rate).toBe(0.5);
  });
});
