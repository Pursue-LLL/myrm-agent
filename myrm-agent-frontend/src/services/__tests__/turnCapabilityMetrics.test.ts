import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { apiRequest } from '@/lib/api';
import {
  __flushTurnCapabilityMetricsForTest,
  __resetTurnCapabilityMetricsForTest,
  getTurnCapabilitySummary,
  recordTurnCapabilityOverrideApplied,
  recordTurnCapabilitySelectionSubmitted,
  recordTurnCapabilitySendFailed,
} from '@/services/turnCapabilityMetrics';

vi.mock('@/lib/api', () => ({
  apiRequest: vi.fn(),
}));

const apiRequestMock = vi.mocked(apiRequest);

describe('turnCapabilityMetrics', () => {
  beforeEach(() => {
    apiRequestMock.mockReset();
    apiRequestMock.mockResolvedValue({ accepted: true });
    __resetTurnCapabilityMetricsForTest();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('posts selection_submitted event in silent mode', async () => {
    recordTurnCapabilitySelectionSubmitted('direct', 2, 1, 'chat:test');
    await __flushTurnCapabilityMetricsForTest();

    expect(apiRequestMock).toHaveBeenCalledWith('/statistics/turn-capability/events', {
      method: 'POST',
      body: JSON.stringify({
        event_type: 'selection_submitted',
        source: 'direct',
        context_key: 'chat:test',
        count: 1,
        selected_skill_count: 2,
        selected_mcp_count: 1,
        effective_skill_count: undefined,
        effective_mcp_count: undefined,
        failure_reason: undefined,
      }),
      silent: true,
    });
  });

  it('flushes dropped telemetry after next successful event', async () => {
    apiRequestMock.mockRejectedValueOnce(new Error('offline'));
    apiRequestMock.mockResolvedValue({ accepted: true });

    recordTurnCapabilitySelectionSubmitted('direct', 1, 1, 'chat:test');
    await __flushTurnCapabilityMetricsForTest();
    recordTurnCapabilityOverrideApplied('direct', 1, 1, 1, 1, 'chat:test');
    await __flushTurnCapabilityMetricsForTest();

    const appliedPayload = JSON.parse(String(apiRequestMock.mock.calls[1]?.[1]?.body));
    const droppedPayload = JSON.parse(String(apiRequestMock.mock.calls[2]?.[1]?.body));

    expect(appliedPayload.event_type).toBe('override_applied');
    expect(droppedPayload.event_type).toBe('dropped_report');
    expect(droppedPayload.count).toBe(1);
  });

  it('posts enum send_failed reason', async () => {
    recordTurnCapabilitySendFailed('queue_drain', 'network_error', 'chat:fail');
    await __flushTurnCapabilityMetricsForTest();

    const payload = JSON.parse(String(apiRequestMock.mock.calls[0]?.[1]?.body));
    expect(payload.event_type).toBe('send_failed');
    expect(payload.failure_reason).toBe('network_error');
    expect(payload.source).toBe('queue_drain');
  });

  it('fetches summary from statistics endpoint', async () => {
    apiRequestMock.mockResolvedValueOnce({
      days: 30,
      retention_days: 90,
      total_events: 10,
      selection_submitted_count: 4,
      override_applied_count: 3,
      override_noop_count: 1,
      queue_enqueued_count: 2,
      send_completed_count: 2,
      send_failed_count: 1,
      busy_requeued_count: 1,
      dropped_event_count: 0,
      apply_rate: 0.75,
      noop_rate: 0.25,
      queue_rate: 0.5,
      completion_rate: 0.6667,
      failure_rate: 0.3333,
      avg_selected_skill_count: 1.5,
      avg_selected_mcp_count: 1,
      avg_effective_skill_count: 1.33,
      avg_effective_mcp_count: 1,
      submitted_by_source: { direct: 2, queue_submit: 1, queue_drain: 0, busy_requeue: 1 },
      applied_by_source: { direct: 2, queue_submit: 0, queue_drain: 1, busy_requeue: 0 },
      completed_by_source: { direct: 1, queue_submit: 0, queue_drain: 1, busy_requeue: 0 },
      failed_by_source: { direct: 1, queue_submit: 0, queue_drain: 0, busy_requeue: 0 },
      failure_reason_breakdown: { network_error: 1 },
    });

    const summary = await getTurnCapabilitySummary();

    expect(apiRequestMock).toHaveBeenCalledWith('/statistics/turn-capability/summary?days=30');
    expect(summary.apply_rate).toBe(0.75);
  });
});
