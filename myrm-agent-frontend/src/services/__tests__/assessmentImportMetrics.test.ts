import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { apiRequest } from '@/lib/api';
import {
  __flushAssessmentImportMetricsForTest,
  __resetAssessmentImportMetricsForTest,
  getAssessmentImportSummary,
  getAssessmentImportValueSummary,
  recordAssessmentImportAttempted,
  recordAssessmentImportFailed,
  recordAssessmentImportSucceeded,
} from '@/services/assessmentImportMetrics';

vi.mock('@/lib/api', () => ({
  apiRequest: vi.fn(),
}));

const apiRequestMock = vi.mocked(apiRequest);

describe('assessmentImportMetrics', () => {
  beforeEach(() => {
    apiRequestMock.mockReset();
    apiRequestMock.mockResolvedValue({ accepted: true });
    __resetAssessmentImportMetricsForTest();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('posts import_attempted event in silent mode', async () => {
    recordAssessmentImportAttempted('manual_input', { contextKey: 'project-alpha' });
    await __flushAssessmentImportMetricsForTest();

    expect(apiRequestMock).toHaveBeenCalledWith('/statistics/assessment-import/events', {
      method: 'POST',
      body: JSON.stringify({
        event_type: 'import_attempted',
        surface: 'project_milestone_panel',
        trigger: 'manual_input',
        context_key: 'project-alpha',
        count: 1,
        failure_reason: undefined,
      }),
      silent: true,
    });
  });

  it('posts import_failed event with failure reason', async () => {
    recordAssessmentImportFailed('recent_candidate', 'artifact_not_found', { contextKey: 'project-beta' });
    await __flushAssessmentImportMetricsForTest();

    const payload = JSON.parse(String(apiRequestMock.mock.calls[0]?.[1]?.body));
    expect(payload.event_type).toBe('import_failed');
    expect(payload.trigger).toBe('recent_candidate');
    expect(payload.failure_reason).toBe('artifact_not_found');
  });

  it('flushes dropped telemetry after next successful event', async () => {
    apiRequestMock.mockRejectedValueOnce(new Error('offline'));
    apiRequestMock.mockResolvedValue({ accepted: true });

    recordAssessmentImportAttempted('manual_input', { contextKey: 'project-gamma' });
    await __flushAssessmentImportMetricsForTest();

    recordAssessmentImportSucceeded('manual_input', { contextKey: 'project-gamma' });
    await __flushAssessmentImportMetricsForTest();

    const succeededPayload = JSON.parse(String(apiRequestMock.mock.calls[1]?.[1]?.body));
    const droppedPayload = JSON.parse(String(apiRequestMock.mock.calls[2]?.[1]?.body));

    expect(succeededPayload.event_type).toBe('import_succeeded');
    expect(droppedPayload.event_type).toBe('dropped_report');
    expect(droppedPayload.trigger).toBe('manual_input');
    expect(droppedPayload.count).toBe(1);
  });

  it('fetches summary from statistics endpoint', async () => {
    apiRequestMock.mockResolvedValueOnce({
      days: 30,
      retention_days: 90,
      total_events: 12,
      import_attempted_count: 5,
      import_succeeded_count: 4,
      import_failed_count: 1,
      dropped_event_count: 2,
      success_rate: 0.8,
      failure_rate: 0.2,
      recent_candidate_attempt_rate: 0.6,
      attempts_by_trigger: { manual_input: 2, recent_candidate: 3 },
      successes_by_trigger: { manual_input: 1, recent_candidate: 3 },
      failures_by_trigger: { manual_input: 1, recent_candidate: 0 },
      failure_reason_breakdown: { artifact_not_found: 1 },
    });

    const summary = await getAssessmentImportSummary(30);

    expect(apiRequestMock).toHaveBeenCalledWith('/statistics/assessment-import/summary?days=30');
    expect(summary.success_rate).toBe(0.8);
  });

  it('fetches value summary with project scope', async () => {
    apiRequestMock.mockResolvedValueOnce({
      days: 30,
      project_id: 'proj-alpha',
      imports_total: 3,
      imports_with_task_completion: 2,
      imports_with_milestone_completion: 1,
      imported_tasks_total: 10,
      completed_tasks_total: 4,
      imported_milestones_total: 5,
      completed_milestones_total: 1,
      task_completion_rate: 0.4,
      milestone_completion_rate: 0.2,
      import_activation_rate: 0.6667,
    });

    const summary = await getAssessmentImportValueSummary(30, 'proj-alpha');

    expect(apiRequestMock).toHaveBeenCalledWith(
      '/statistics/assessment-import/value-summary?days=30&project_id=proj-alpha',
    );
    expect(summary.task_completion_rate).toBe(0.4);
  });
});
