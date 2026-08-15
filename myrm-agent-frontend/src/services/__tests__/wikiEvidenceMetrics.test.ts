import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { apiRequest } from '@/lib/api';
import {
  __flushWikiEvidenceMetricsForTest,
  __resetWikiEvidenceMetricsForTest,
  getWikiEvidenceSummary,
  recordEvidenceSurface,
  recordQualityOutcomeNegative,
  recordSnippetClose,
  recordSnippetOpen,
  recordWikiQueryAttempt,
  recordWikiQuerySubmitted,
} from '@/services/wiki/evidenceMetrics';

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

  it('marks only first successful query after evidence interaction as requery', async () => {
    recordSnippetOpen('chat', 'L1');
    vi.advanceTimersByTime(2500);
    recordSnippetClose('chat', 2500);

    recordWikiQueryAttempt('settings');
    recordWikiQuerySubmitted('settings');
    recordWikiQuerySubmitted('settings');
    await __flushWikiEvidenceMetricsForTest();

    const attemptCall = apiRequestMock.mock.calls[2];
    const firstQueryCall = apiRequestMock.mock.calls[3];
    const secondQueryCall = apiRequestMock.mock.calls[4];
    expect(attemptCall).toBeDefined();
    expect(firstQueryCall).toBeDefined();
    expect(secondQueryCall).toBeDefined();

    const attemptPayload = JSON.parse(String(attemptCall?.[1]?.body));
    const firstPayload = JSON.parse(String(firstQueryCall?.[1]?.body));
    const secondPayload = JSON.parse(String(secondQueryCall?.[1]?.body));

    expect(attemptPayload.event_type).toBe('query_attempted');
    expect(attemptPayload.after_evidence).toBeUndefined();
    expect(firstPayload.after_evidence).toBe(true);
    expect(secondPayload.after_evidence).toBe(false);
  });

  it('flushes dropped events after next successful post', async () => {
    apiRequestMock.mockRejectedValueOnce(new Error('offline'));
    apiRequestMock.mockResolvedValue({ accepted: true });

    recordSnippetOpen('chat', 'L1', 'agent:test');
    await __flushWikiEvidenceMetricsForTest();
    recordWikiQuerySubmitted('chat', 'agent:test');
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

  it('records turn_distance for query attempt and success events', async () => {
    recordWikiQueryAttempt('chat', 'chat:ctx', 2.9);
    recordWikiQuerySubmitted('chat', 'chat:ctx', 3.2);
    await __flushWikiEvidenceMetricsForTest();

    const attemptPayload = JSON.parse(String(apiRequestMock.mock.calls[0]?.[1]?.body));
    const successPayload = JSON.parse(String(apiRequestMock.mock.calls[1]?.[1]?.body));

    expect(attemptPayload).toMatchObject({
      event_type: 'query_attempted',
      turn_distance: 2,
      context_key: 'chat:ctx',
    });
    expect(successPayload).toMatchObject({
      event_type: 'query_submitted',
      turn_distance: 3,
      context_key: 'chat:ctx',
    });
  });

  it('posts negative quality outcome events for evidence answers', async () => {
    recordQualityOutcomeNegative('chat', 2, 'chat:test-session');
    await __flushWikiEvidenceMetricsForTest();

    expect(apiRequestMock).toHaveBeenCalledWith('/statistics/wiki-evidence/events', {
      method: 'POST',
      body: JSON.stringify({
        event_type: 'quality_outcome_negative',
        surface: 'chat',
        context_key: 'chat:test-session',
        count: 2,
      }),
      silent: true,
    });
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
      quality_outcome_negative_count: 1,
      quality_outcome_negative_rate: 0.25,
      query_attempt_count: 3,
      query_success_count: 2,
      query_success_rate: 0.6667,
      query_count: 2,
      requery_count: 1,
      requery_rate: 0.5,
      verification_dwell_avg_ms: 1234,
      verification_dwell_sample_count: 2,
      snippet_open_by_surface: { chat: 1, settings: 1 },
      snippet_open_by_level: { L0: 0, L1: 1, L2: 1 },
      quality_outcome_negative_by_surface: { chat: 1, settings: 0 },
    });

    const result = await getWikiEvidenceSummary();

    expect(apiRequestMock).toHaveBeenCalledWith('/statistics/wiki-evidence/summary?days=30');
    expect(result.requery_rate).toBe(0.5);
  });
});
