import { describe, expect, it } from 'vitest';
import { CRON_OVERDUE_THRESHOLD_MS, isCronOverdue } from '../cron-utils';
import type { CronJob } from '@/services/cron.types';

function makeJob(overrides: Partial<CronJob>): CronJob {
  return {
    id: 'job-1',
    user_id: 'user-1',
    name: 'Test Job',
    job_type: 'agent',
    status: 'active',
    schedule: { kind: 'interval', interval_ms: 3_600_000 },
    context_from: [],
    max_retries: 3,
    retry_backoff_ms: 0,
    timeout_seconds: 600,
    misfire_grace_seconds: 300,
    cooldown_seconds: 0,
    fire_count: 0,
    session_target: 'isolated',
    required_capabilities: [],
    tools_allowed: [],
    allowed_roots: [],
    delete_after_run: false,
    run_retention_days: 30,
    deduplicate: false,
    skip_if_active: false,
    consecutive_failures: 0,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    ...overrides,
  };
}

describe('isCronOverdue', () => {
  const now = Date.parse('2026-01-10T12:00:00Z');
  const justLate = new Date(now - CRON_OVERDUE_THRESHOLD_MS - 1_000).toISOString();
  const onTime = new Date(now + 60_000).toISOString();

  it('是 active 且 next_run 已过阈值 → true', () => {
    expect(isCronOverdue(makeJob({ next_run_at: justLate }), now)).toBe(true);
  });

  it('next_run 仍未来 → false', () => {
    expect(isCronOverdue(makeJob({ next_run_at: onTime }), now)).toBe(false);
  });

  it('暂停任务不算 overdue', () => {
    expect(isCronOverdue(makeJob({ status: 'paused', next_run_at: justLate }), now)).toBe(false);
  });

  it('已完成任务不算 overdue', () => {
    expect(isCronOverdue(makeJob({ status: 'completed', next_run_at: justLate }), now)).toBe(false);
  });

  it('一次性任务不算 overdue（无周期预期）', () => {
    expect(
      isCronOverdue(
        makeJob({ schedule: { kind: 'once' }, next_run_at: justLate }),
        now,
      ),
    ).toBe(false);
  });

  it('无 next_run_at → false', () => {
    expect(isCronOverdue(makeJob({ next_run_at: undefined }), now)).toBe(false);
  });
});