import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { apiRequest } from '@/lib/api';
import {
  __flushExpertSummonMetricsForTest,
  __resetExpertSummonMetricsForTest,
  getExpertSummonSummary,
  recordExpertCouncilConsensusReached,
  recordExpertCouncilPhaseCompleted,
  recordExpertRebuttalEffective,
  recordExpertSummonAttempted,
  recordExpertSummonSearchUsed,
  recordExpertSummonSucceeded,
} from '@/services/expertSummonMetrics';

const apiRequestMock = vi.fn();

vi.mock('@/lib/api', () => ({
  apiRequest: (...args: unknown[]) => apiRequestMock(...args),
}));

describe('expertSummonMetrics', () => {
  beforeEach(() => {
    apiRequestMock.mockReset();
    apiRequestMock.mockResolvedValue({ accepted: true });
    __resetExpertSummonMetricsForTest();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('posts summon_attempted event in silent mode', async () => {
    recordExpertSummonAttempted('template_market', 'use_case_chip', {
      contextKey: 'template-market',
      templateKind: 'team',
      fromSearch: true,
      usedUseCase: true,
    });
    await __flushExpertSummonMetricsForTest();

    expect(apiRequestMock).toHaveBeenCalledWith('/statistics/expert-summon/events', {
      method: 'POST',
      body: JSON.stringify({
        event_type: 'summon_attempted',
        surface: 'template_market',
        context_key: 'template-market',
        count: 1,
        trigger: 'use_case_chip',
        template_kind: 'team',
        from_search: true,
        used_use_case: true,
        query_length: undefined,
        failure_reason: undefined,
      }),
      silent: true,
    });
  });

  it('flushes dropped telemetry after next successful event', async () => {
    apiRequestMock.mockRejectedValueOnce(new Error('offline'));
    apiRequestMock.mockResolvedValue({ accepted: true });

    recordExpertSummonAttempted('flow_pad_inline', 'template_card', {
      contextKey: 'flowpad:inline',
      templateKind: 'team',
      fromSearch: false,
      usedUseCase: false,
    });
    await __flushExpertSummonMetricsForTest();

    recordExpertSummonSucceeded('flow_pad_inline', 'template_card', {
      contextKey: 'flowpad:inline',
      templateKind: 'team',
      fromSearch: false,
      usedUseCase: false,
    });
    await __flushExpertSummonMetricsForTest();

    const succeededPayload = JSON.parse(String(apiRequestMock.mock.calls[1]?.[1]?.body));
    const droppedPayload = JSON.parse(String(apiRequestMock.mock.calls[2]?.[1]?.body));

    expect(succeededPayload.event_type).toBe('summon_succeeded');
    expect(droppedPayload.event_type).toBe('dropped_report');
    expect(droppedPayload.surface).toBe('flow_pad_inline');
    expect(droppedPayload.count).toBe(1);
  });

  it('posts search_used with query length', async () => {
    recordExpertSummonSearchUsed('template_market', 23, 'template-market');
    await __flushExpertSummonMetricsForTest();

    const payload = JSON.parse(String(apiRequestMock.mock.calls[0]?.[1]?.body));
    expect(payload.event_type).toBe('search_used');
    expect(payload.query_length).toBe(23);
    expect(payload.surface).toBe('template_market');
  });

  it('fetches summary from statistics endpoint', async () => {
    apiRequestMock.mockResolvedValueOnce({
      days: 30,
      retention_days: 90,
      total_events: 14,
      surface_viewed_count: 2,
      search_used_count: 2,
      summon_attempted_count: 4,
      summon_succeeded_count: 3,
      summon_failed_count: 1,
      route_applied_count: 2,
      route_apply_failed_count: 1,
      first_message_sent_count: 2,
      dropped_event_count: 0,
      summon_success_rate: 0.75,
      summon_failure_rate: 0.25,
      route_apply_rate: 0.6667,
      first_message_sent_rate: 0.6667,
      use_case_trigger_rate: 0.5,
      search_assisted_summon_rate: 0.5,
      avg_search_query_length: 15.5,
      viewed_by_surface: { template_market: 1, flow_pad_inline: 1 },
      attempted_by_surface: { template_market: 2, flow_pad_inline: 2 },
      succeeded_by_surface: { template_market: 2, flow_pad_inline: 1 },
      failed_by_surface: { template_market: 0, flow_pad_inline: 1 },
      attempted_by_trigger: { template_card: 2, use_case_chip: 2, route_menu: 0 },
      failure_reason_breakdown: { network_error: 1 },
    });

    const summary = await getExpertSummonSummary();

    expect(apiRequestMock).toHaveBeenCalledWith('/statistics/expert-summon/summary?days=30');
    expect(summary.summon_success_rate).toBe(0.75);
  });

  it('posts council phase, consensus, and rebuttal events', async () => {
    recordExpertCouncilPhaseCompleted('flow_pad_inline', 'plus_popover_card', {
      contextKey: 'council:session:1',
      templateKind: 'team',
    });
    recordExpertCouncilConsensusReached('flow_pad_inline', 'plus_popover_card', {
      contextKey: 'council:session:1',
      templateKind: 'team',
    });
    recordExpertRebuttalEffective('flow_pad_inline', 'plus_popover_card', {
      contextKey: 'council:session:1',
      templateKind: 'team',
    });

    await __flushExpertSummonMetricsForTest();

    expect(apiRequestMock).toHaveBeenCalledTimes(3);
    const p1 = JSON.parse(String(apiRequestMock.mock.calls[0]?.[1]?.body));
    const p2 = JSON.parse(String(apiRequestMock.mock.calls[1]?.[1]?.body));
    const p3 = JSON.parse(String(apiRequestMock.mock.calls[2]?.[1]?.body));

    expect(p1.event_type).toBe('council_phase_completed');
    expect(p2.event_type).toBe('council_consensus_reached');
    expect(p3.event_type).toBe('expert_rebuttal_effective');
    expect(p1.trigger).toBe('plus_popover_card');
  });
});
