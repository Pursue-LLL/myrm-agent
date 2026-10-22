/**
 * Client service layer for Run State Multi-Surface Projections.
 * Implements REST calls to /api/v1/runs with resilient local fallback for tests.
 */

import {
  AttemptRecord,
  RunProjectionEvent,
  RunStateSnapshot,
  SurfaceViewType,
} from './runtimeProjectionTypes';

const API_BASE = '/api/v1/runs';

const fallbackSnapshot: RunStateSnapshot = {
  run_id: 'run_mateclaw_demo_001',
  title: 'Enterprise Microservice State Projection Refactor',
  status: 'completed',
  active_surface: 'runtime_console',
  current_attempt: 2,
  attempts: [
    {
      attempt_id: 'att_demo_01',
      run_id: 'run_mateclaw_demo_001',
      attempt_number: 1,
      status: 'failed',
      started_at_ms: Date.now() - 12000,
      finished_at_ms: Date.now() - 8500,
      duration_ms: 3500,
      tokens_in: 1420,
      tokens_out: 210,
      tokens_per_sec: 60.0,
      error_reason: 'ProviderRateLimitError: 429 Too Many Requests on primary endpoint',
      stack_trace: 'Traceback (most recent call last):\nRateLimitError: 429',
      diff_summary: '0 files mutated',
    },
    {
      attempt_id: 'att_demo_02',
      run_id: 'run_mateclaw_demo_001',
      attempt_number: 2,
      status: 'completed',
      started_at_ms: Date.now() - 8000,
      finished_at_ms: Date.now() - 1500,
      duration_ms: 6500,
      tokens_in: 2890,
      tokens_out: 1450,
      tokens_per_sec: 223.1,
      error_reason: null,
      stack_trace: null,
      diff_summary: '3 files mutated (+128, -14 lines)',
    },
  ],
  deliverables: [
    {
      deliverable_id: 'deliv_01',
      title: 'Async Event Stream Projection Engine',
      type: 'source_code',
      path_or_uri: 'src/components/features/runtime/useRunProjection.ts',
      status: 'verified',
      created_at_ms: Date.now() - 1500,
    },
  ],
  audit_entries: [
    {
      audit_id: 'audit_01',
      action: 'file_mutation',
      actor: 'myrm_agent_runtime',
      risk_level: 'low',
      decision: 'approved',
      timestamp_ms: Date.now() - 3000,
    },
  ],
  events: [
    {
      event_id: 'evt_01',
      run_id: 'run_mateclaw_demo_001',
      event_type: 'run_initialized',
      timestamp_ms: Date.now() - 12000,
      payload: { title: 'Enterprise Microservice State Projection Refactor' },
    },
  ],
  total_tokens: 5970,
  avg_tokens_per_sec: 141.55,
};

export const runtimeProjectionService = {
  async getRunProjection(runId: string): Promise<RunStateSnapshot> {
    try {
      const res = await fetch(`${API_BASE}/${runId}/projection`);
      if (res.ok) {
        return (await res.json()) as RunStateSnapshot;
      }
    } catch {
      // Fallback
    }
    return { ...fallbackSnapshot, run_id: runId };
  },

  async getRunEvents(runId: string, sinceMs = 0): Promise<RunProjectionEvent[]> {
    try {
      const res = await fetch(`${API_BASE}/${runId}/events?since_ms=${sinceMs}`);
      if (res.ok) {
        return (await res.json()) as RunProjectionEvent[];
      }
    } catch {
      // Fallback
    }
    return fallbackSnapshot.events.filter((e) => e.timestamp_ms >= sinceMs);
  },

  async switchSurface(runId: string, surface: SurfaceViewType): Promise<boolean> {
    try {
      const res = await fetch(`${API_BASE}/${runId}/switch-surface`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ surface }),
      });
      if (res.ok) {
        return true;
      }
    } catch {
      // Fallback
    }
    fallbackSnapshot.active_surface = surface;
    return true;
  },

  async recordAttempt(
    runId: string,
    attempt: Partial<AttemptRecord> & { attempt_number: number }
  ): Promise<AttemptRecord> {
    try {
      const res = await fetch(`${API_BASE}/${runId}/attempts`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(attempt),
      });
      if (res.ok) {
        return (await res.json()) as AttemptRecord;
      }
    } catch {
      // Fallback
    }

    const newRecord: AttemptRecord = {
      attempt_id: `att_mock_${Date.now()}`,
      run_id: runId,
      attempt_number: attempt.attempt_number,
      status: attempt.status ?? 'completed',
      started_at_ms: Date.now() - 2000,
      finished_at_ms: Date.now(),
      duration_ms: attempt.duration_ms ?? 2000,
      tokens_in: attempt.tokens_in ?? 500,
      tokens_out: attempt.tokens_out ?? 200,
      tokens_per_sec: attempt.tokens_per_sec ?? 120.0,
      error_reason: attempt.error_reason,
      stack_trace: attempt.stack_trace,
      diff_summary: attempt.diff_summary ?? '1 file changed',
    };

    fallbackSnapshot.attempts.push(newRecord);
    fallbackSnapshot.current_attempt = attempt.attempt_number;
    return newRecord;
  },
};
