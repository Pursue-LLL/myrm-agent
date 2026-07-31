import { describe, expect, it, vi, beforeEach } from 'vitest';
import type { CronJob } from '@/services/cron.types';
import {
  canDismissSettingsAuditFlow,
  needsSettingsAuditGate,
  prepareJobForSettingsAudit,
  resumeJobAfterAuditConfirm,
} from '@/lib/cron/cronCreateAuditGate';
import { markCronAuditConfirmed } from '@/lib/cron/buildCronAuditFields';

vi.mock('@/services/cron', () => ({
  pauseCronJob: vi.fn(),
  resumeCronJob: vi.fn(),
  getCronJob: vi.fn(),
}));

import { getCronJob, pauseCronJob, resumeCronJob } from '@/services/cron';

const baseJob: CronJob = {
  id: 'job-1',
  user_id: 'default',
  name: 'Digest',
  job_type: 'agent',
  status: 'active',
  schedule: { kind: 'cron', expr: '0 9 * * *', tz: 'UTC' },
  max_retries: 0,
  retry_backoff_ms: 0,
  timeout_seconds: 600,
  misfire_grace_seconds: 60,
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
};

describe('cronCreateAuditGate', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
  });

  it('pauses active jobs before settings audit', async () => {
    vi.mocked(pauseCronJob).mockResolvedValue(undefined);
    vi.mocked(getCronJob).mockResolvedValue({ ...baseJob, status: 'paused' });

    const result = await prepareJobForSettingsAudit(baseJob);

    expect(pauseCronJob).toHaveBeenCalledWith('job-1');
    expect(result.status).toBe('paused');
  });

  it('skips pause when job is already paused', async () => {
    const paused = { ...baseJob, status: 'paused' as const };

    const result = await prepareJobForSettingsAudit(paused);

    expect(pauseCronJob).not.toHaveBeenCalled();
    expect(result.status).toBe('paused');
  });

  it('resumes job after audit confirm', async () => {
    vi.mocked(resumeCronJob).mockResolvedValue(undefined);
    vi.mocked(getCronJob).mockResolvedValue({ ...baseJob, status: 'active' });

    const result = await resumeJobAfterAuditConfirm('job-1');

    expect(resumeCronJob).toHaveBeenCalledWith('job-1');
    expect(result.status).toBe('active');
  });

  it('needs settings gate when paused and not confirmed', () => {
    const paused = { ...baseJob, status: 'paused' as const };
    expect(needsSettingsAuditGate(paused)).toBe(true);
    markCronAuditConfirmed('job-1');
    expect(needsSettingsAuditGate(paused)).toBe(false);
  });

  it('can dismiss settings audit only after confirm and active', () => {
    const paused = { ...baseJob, status: 'paused' as const };
    expect(canDismissSettingsAuditFlow(paused)).toBe(false);
    markCronAuditConfirmed('job-1');
    expect(canDismissSettingsAuditFlow({ ...baseJob, status: 'active' })).toBe(true);
  });
});
