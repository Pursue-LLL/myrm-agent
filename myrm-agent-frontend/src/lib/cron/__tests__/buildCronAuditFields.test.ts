import { describe, expect, it } from 'vitest';
import type { CronJob } from '@/services/cron.types';
import { buildCronAuditFields } from '@/lib/cron/buildCronAuditFields';

const baseJob: CronJob = {
  id: 'job-1',
  user_id: 'default',
  name: 'Weekly digest',
  job_type: 'agent',
  status: 'active',
  schedule: { kind: 'cron', expr: '0 9 * * 1', tz: 'Asia/Shanghai' },
  prompt: 'Summarize inbox',
  agent_id: 'agent-a',
  context_from: ['job-prev'],
  delivery: { channel: 'chat', target: null },
  failure_alert: { enabled: true, after: 3, cooldown_seconds: 3600 },
  failure_delivery: { channel: 'chat', target: null },
  max_retries: 0,
  retry_backoff_ms: 0,
  timeout_seconds: 600,
  misfire_grace_seconds: 60,
  cooldown_seconds: 0,
  fire_count: 0,
  session_target: 'isolated',
  required_capabilities: [],
  tools_allowed: ['web_fetch_tool'],
  allowed_roots: [],
  delete_after_run: false,
  run_retention_days: 30,
  deduplicate: false,
  skip_if_active: false,
  consecutive_failures: 1,
  last_error: 'timeout',
  acceptance_criteria: [{ type: 'semantic', description: 'has summary' }],
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
};

describe('buildCronAuditFields', () => {
  it('returns six Hermes-style audit fields', () => {
    const fields = buildCronAuditFields(baseJob);
    expect(fields).toHaveLength(6);
    expect(fields.map((f) => f.id)).toEqual([
      'taskName',
      'scheduleTz',
      'skillsInvoked',
      'inputSources',
      'outputDestinations',
      'failureRecords',
    ]);
  });

  it('includes schedule timezone and tool bindings', () => {
    const fields = buildCronAuditFields(baseJob);
    expect(fields[0]?.value).toBe('Weekly digest');
    expect(fields[1]?.value).toContain('Asia/Shanghai');
    expect(fields[2]?.value).toContain('web_fetch_tool');
    expect(fields[3]?.value).toContain('context_from: job-prev');
    expect(fields[4]?.value).toContain('acceptance: 1 rule(s)');
    expect(fields[5]?.value).toContain('retention: 30d');
  });
});
