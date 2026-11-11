import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { ApiError } from '@/lib/api';
import {
  __flushExpertSummonMetricsForTest,
  __resetExpertSummonMetricsForTest,
  getExpertSummonSummary,
  inferExpertSummonFailureReason,
  recordExpertCouncilConsensusReached,
  recordExpertCouncilPhaseCompleted,
  recordExpertRebuttalEffective,
  recordExpertSummonAttempted,
  recordExpertSummonFailed,
  recordExpertSummonFirstMessageSent,
  recordExpertSummonRouteApplied,
  recordExpertSummonRouteApplyFailed,
  recordExpertSummonSearchUsed,
  recordExpertSummonSucceeded,
  recordExpertSummonSurfaceViewed,
} from '@/services/expertSummonMetrics';

const apiRequestMock = vi.fn();

vi.mock('@/lib/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/api')>()),
  apiRequest: (...args: unknown[]) => apiRequestMock(...args),
}));

/** The body of the n-th request the metrics client sent. */
const sentPayload = (index: number) => JSON.parse(String(apiRequestMock.mock.calls[index]?.[1]?.body));

const FUNNEL_OPTIONS = { contextKey: 'ctx', templateKind: 'team', fromSearch: true, usedUseCase: false } as const;
const FUNNEL_FIELDS = {
  context_key: 'ctx',
  trigger: 'template_card',
  template_kind: 'team',
  from_search: true,
  used_use_case: false,
};

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

  describe('events of the summon funnel', () => {
    it.each([
      [
        'surface viewed',
        () => recordExpertSummonSurfaceViewed('template_market', 'ctx'),
        { event_type: 'surface_viewed', surface: 'template_market', context_key: 'ctx' },
      ],
      [
        'summon attempted',
        () => recordExpertSummonAttempted('flow_pad_inline', 'template_card', FUNNEL_OPTIONS),
        { event_type: 'summon_attempted', surface: 'flow_pad_inline', ...FUNNEL_FIELDS },
      ],
      [
        'summon succeeded',
        () => recordExpertSummonSucceeded('flow_pad_inline', 'template_card', FUNNEL_OPTIONS),
        { event_type: 'summon_succeeded', surface: 'flow_pad_inline', ...FUNNEL_FIELDS },
      ],
      [
        'summon failed',
        () => recordExpertSummonFailed('flow_pad_inline', 'template_card', 'server_error', FUNNEL_OPTIONS),
        { event_type: 'summon_failed', surface: 'flow_pad_inline', failure_reason: 'server_error', ...FUNNEL_FIELDS },
      ],
      [
        'route applied',
        () => recordExpertSummonRouteApplied('flow_pad_inline', 'template_card', FUNNEL_OPTIONS),
        { event_type: 'route_applied', surface: 'flow_pad_inline', ...FUNNEL_FIELDS },
      ],
      [
        'route apply failed',
        () => recordExpertSummonRouteApplyFailed('flow_pad_inline', 'template_card', FUNNEL_OPTIONS),
        {
          event_type: 'route_apply_failed',
          surface: 'flow_pad_inline',
          failure_reason: 'route_apply_failed',
          ...FUNNEL_FIELDS,
        },
      ],
      [
        'first message sent',
        () => recordExpertSummonFirstMessageSent('flow_pad_inline', 'template_card', FUNNEL_OPTIONS),
        { event_type: 'first_message_sent', surface: 'flow_pad_inline', ...FUNNEL_FIELDS },
      ],
    ])('posts one %s event with what the caller knows about it', async (_name, record, expected) => {
      record();
      await __flushExpertSummonMetricsForTest();

      expect(apiRequestMock).toHaveBeenCalledOnce();
      expect(sentPayload(0)).toEqual({ count: 1, ...expected });
    });

    it('posts search_used with query length', async () => {
      recordExpertSummonSearchUsed('template_market', 23, 'template-market');
      await __flushExpertSummonMetricsForTest();

      const payload = sentPayload(0);
      expect(payload.event_type).toBe('search_used');
      expect(payload.query_length).toBe(23);
      expect(payload.surface).toBe('template_market');
    });

    it.each([
      [Number.NaN, 0],
      [-5, 0],
      [12.7, 12],
      [999, 200],
    ])('sends a query length of %s as %i, within what the server accepts', async (given, sent) => {
      recordExpertSummonSearchUsed('template_market', given);
      await __flushExpertSummonMetricsForTest();

      expect(sentPayload(0).query_length).toBe(sent);
    });

    it.each([
      [undefined, 'global'],
      ['   ', 'global'],
      ['  council:7  ', 'council:7'],
    ])('files an event under the context %j as "%s"', async (given, filed) => {
      recordExpertSummonSurfaceViewed('template_market', given);
      await __flushExpertSummonMetricsForTest();

      expect(sentPayload(0).context_key).toBe(filed);
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
      expect([0, 1, 2].map((index) => sentPayload(index).event_type)).toEqual([
        'council_phase_completed',
        'council_consensus_reached',
        'expert_rebuttal_effective',
      ]);
      expect(sentPayload(0)).toMatchObject({ trigger: 'plus_popover_card', template_kind: 'team' });
    });
  });

  describe('summary', () => {
    it('fetches summary from statistics endpoint', async () => {
      apiRequestMock.mockResolvedValueOnce({ summon_success_rate: 0.75 });

      const summary = await getExpertSummonSummary();

      expect(apiRequestMock).toHaveBeenCalledWith('/statistics/expert-summon/summary?days=30');
      expect(summary.summon_success_rate).toBe(0.75);
    });

    it('asks for the window the caller names', async () => {
      await getExpertSummonSummary(7);

      expect(apiRequestMock).toHaveBeenCalledWith('/statistics/expert-summon/summary?days=7');
    });
  });

  describe('why a summon failed', () => {
    const apiError = (message: string, code: number, businessCode?: string) =>
      new ApiError(message, code, [], undefined, businessCode);

    it.each([
      {
        name: 'a request the user cancelled',
        error: new DOMException('aborted', 'AbortError'),
        reason: 'unknown_error',
      },
      {
        name: 'a fetch that never reached the server',
        error: new TypeError('Failed to fetch'),
        reason: 'network_error',
      },
      {
        name: 'a server nobody could connect to',
        error: apiError('无法连接到服务器，请检查服务是否启动', 50003, 'NETWORK_ERROR'),
        reason: 'network_error',
      },
      {
        name: 'a request that timed out',
        error: apiError('请求超时，请检查网络连接或稍后重试', 40408, 'TIMEOUT_ERROR'),
        reason: 'network_error',
      },
      {
        name: 'a local backend that is not running',
        error: apiError('Backend is down', 503, 'BACKEND_UNREACHABLE'),
        reason: 'network_error',
      },
      {
        name: 'a 5xx answer without saying why',
        error: apiError('Something broke', 500, '50001'),
        reason: 'server_error',
      },
      {
        name: 'a 4xx answer that happens to contain a 5',
        error: apiError('Template 15 is invalid', 422, '42201'),
        reason: 'unknown_error',
      },
      { name: 'a refused request', error: apiError('Agent quota exceeded', 403, '40301'), reason: 'unknown_error' },
      {
        name: 'an error that speaks of the network',
        error: new Error('Network request failed'),
        reason: 'network_error',
      },
      {
        name: 'an error naming a 5xx status',
        error: new Error('Request failed with status code 503'),
        reason: 'server_error',
      },
      { name: 'an error blaming the server', error: new Error('Internal Server Error'), reason: 'server_error' },
      {
        name: 'an error with a 5 elsewhere in its text',
        error: new Error('Template 15 not found'),
        reason: 'unknown_error',
      },
      { name: 'a thrown string', error: 'boom', reason: 'unknown_error' },
      { name: 'nothing at all', error: undefined, reason: 'unknown_error' },
    ])('classifies $name as $reason', ({ error, reason }) => {
      expect(inferExpertSummonFailureReason(error)).toBe(reason);
    });
  });
});
