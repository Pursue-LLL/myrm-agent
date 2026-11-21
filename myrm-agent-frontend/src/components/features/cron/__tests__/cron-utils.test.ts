import { describe, expect, it, vi } from 'vitest';
import {
  CRON_OVERDUE_THRESHOLD_MS,
  computeStats,
  connectorCategoryHintKey,
  connectorCategoryLabelKey,
  filterJobs,
  formatRelativeTime,
  formatTimeoutSeconds,
  isCronOverdue,
  isFailedRunStatus,
  isFailingJob,
  parseTimeoutSeconds,
  pauseReasonLabelKey,
  runStatusLabelKey,
  skipReasonLabelKey,
  statusBorderColor,
  triggerSourceLabelKey,
} from '../cron-utils';
import type { CronJob, PauseReason, RunStatus } from '@/services/cron.types';

function makeJob(overrides: Partial<CronJob>): CronJob {
  return {
    id: 'job-1',
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
    expect(isCronOverdue(makeJob({ schedule: { kind: 'once' }, next_run_at: justLate }), now)).toBe(false);
  });

  it('无 next_run_at → false', () => {
    expect(isCronOverdue(makeJob({ next_run_at: undefined }), now)).toBe(false);
  });

  it('misfire_grace 大于基础阈值时，grace 内不算 overdue（对齐后端可补跑）', () => {
    const graceLate = new Date(now - 11 * 60_000).toISOString(); // 错过 11min < grace 15min
    const job = makeJob({ misfire_grace_seconds: 900, next_run_at: graceLate });
    expect(isCronOverdue(job, now)).toBe(false);
  });

  it('misfire_grace 大于基础阈值时，超过 grace 才算 overdue', () => {
    const pastGrace = new Date(now - 16 * 60_000).toISOString(); // 错过 16min > grace 15min
    const job = makeJob({ misfire_grace_seconds: 900, next_run_at: pastGrace });
    expect(isCronOverdue(job, now)).toBe(true);
  });
});

describe('formatRelativeTime', () => {
  const now = Date.parse('2026-01-10T12:00:00Z');
  const locale = 'en-US';
  const t = vi.fn((key: string, values?: Record<string, number>) => {
    if (key === 'relativeDate.justNow') {
      return 'just now';
    }
    if (key === 'relativeDate.minutesAgo') {
      return `${values?.count}m ago`;
    }
    if (key === 'relativeDate.hoursAgo') {
      return `${values?.count}h ago`;
    }
    if (key === 'relativeDate.daysAgo') {
      return `${values?.count}d ago`;
    }
    return key;
  });

  it('不到 1 分钟 → just now', () => {
    expect(formatRelativeTime(new Date(now - 30_000).toISOString(), t, locale, now)).toBe('just now');
    expect(t).toHaveBeenCalledWith('relativeDate.justNow');
  });

  it('分钟级 → {count}m ago', () => {
    expect(formatRelativeTime(new Date(now - 3 * 60_000).toISOString(), t, locale, now)).toBe('3m ago');
    expect(t).toHaveBeenCalledWith('relativeDate.minutesAgo', { count: 3 });
  });

  it('小时级 → {count}h ago', () => {
    expect(formatRelativeTime(new Date(now - 5 * 3_600_000).toISOString(), t, locale, now)).toBe('5h ago');
    expect(t).toHaveBeenCalledWith('relativeDate.hoursAgo', { count: 5 });
  });

  it('天级 → {count}d ago', () => {
    expect(formatRelativeTime(new Date(now - 3 * 86_400_000).toISOString(), t, locale, now)).toBe('3d ago');
    expect(t).toHaveBeenCalledWith('relativeDate.daysAgo', { count: 3 });
  });

  it('超过 7 天 → 回退为短日期（month/day）', () => {
    const old = new Date(now - 10 * 86_400_000).toISOString();
    const expected = new Intl.DateTimeFormat(locale, { month: 'short', day: 'numeric' }).format(now - 10 * 86_400_000);
    expect(formatRelativeTime(old, t, locale, now)).toBe(expected);
  });

  it('未来时间戳 → just now（时钟偏差容错）', () => {
    expect(formatRelativeTime(new Date(now + 5 * 60_000).toISOString(), t, locale, now)).toBe('just now');
    expect(t).toHaveBeenCalledWith('relativeDate.justNow');
  });

  it('非法时间戳 → 空字符串', () => {
    expect(formatRelativeTime('not-a-date', t, locale, now)).toBe('');
  });
});

describe('parseTimeoutSeconds', () => {
  it.each([
    ['10', 10],
    ['300', 300],
    [' 900 ', 900],
    ['3600', 3600],
  ])('accepts %j as %i seconds', (typed, seconds) => {
    expect(parseTimeoutSeconds(typed)).toBe(seconds);
  });

  it.each(['', '  ', '9', '3601', '1.5', '-30', '1e3', '0x20', 'abc', '30s'])('rejects %j', (typed) => {
    expect(parseTimeoutSeconds(typed)).toBeNull();
  });
});

describe('formatTimeoutSeconds', () => {
  it.each([
    [45, '45s'],
    [60, '1m'],
    [90, '1m 30s'],
    [300, '5m'],
    [3600, '1h'],
    [3690, '1h 1m 30s'],
    [0, '0s'],
  ])('writes %i seconds as %s', (seconds, text) => {
    expect(formatTimeoutSeconds(seconds)).toBe(text);
  });
});

describe('skipReasonLabelKey', () => {
  it.each([
    ['usage_limit', 'skippedUsageLimit'],
    ['budget_blocked', 'skippedBudgetBlocked'],
    ['credit_exhausted', 'skippedCreditExhausted'],
    ['pre-flight-condition', 'skippedPreflight'],
    ['no-content', 'skippedNoContent'],
    ['cooldown_active', 'skippedCooldown'],
    ['outside_active_hours', 'skippedOutsideHours'],
    ['untrusted-workflow', 'skippedUntrustedWorkflow'],
    ['memory_pressure:critical', 'skippedMemoryPressure'],
    ['memory_pressure:emergency', 'skippedMemoryPressure'],
  ])('labels the code %s with %s', (code, labelKey) => {
    expect(skipReasonLabelKey(code)).toBe(labelKey);
  });

  it.each([undefined, '', 'made-up-code', 'memory_pressure:low', 'constructor', 'toString', '__proto__'])(
    'has no label for %j',
    (output) => {
      expect(skipReasonLabelKey(output)).toBeUndefined();
    },
  );
});

describe('triggerSourceLabelKey', () => {
  it.each([
    ['cron', 'triggerSourceCron'],
    ['event', 'triggerSourceEvent'],
    ['webhook', 'triggerSourceWebhook'],
    ['system_event', 'triggerSourceSystem'],
    ['manual', 'triggerSourceManual'],
    ['recovery', 'triggerSourceRecovery'],
    ['shutdown', 'triggerSourceShutdown'],
  ])('labels the source %s with %s', (source, labelKey) => {
    expect(triggerSourceLabelKey(source)).toBe(labelKey);
  });

  it.each(['', 'made-up-source', 'constructor', 'toString', '__proto__'])('has no label for %j', (source) => {
    expect(triggerSourceLabelKey(source)).toBeUndefined();
  });
});

describe('connectorCategoryLabelKey and connectorCategoryHintKey', () => {
  it.each([
    ['auth_failure', 'connectorCategoryAuth', 'connectorCategoryAuthHint'],
    ['http_client_error', 'connectorCategoryClient', 'connectorCategoryClientHint'],
    ['http_server_error', 'connectorCategoryServer', 'connectorCategoryServerHint'],
    ['timeout', 'connectorCategoryTimeout', 'connectorCategoryTimeoutHint'],
    ['network_unreachable', 'connectorCategoryNetwork', 'connectorCategoryNetworkHint'],
    ['payload_contract', 'connectorCategoryPayload', 'connectorCategoryPayloadHint'],
    ['address_rejected', 'connectorCategoryAddress', 'connectorCategoryAddressHint'],
    ['unknown', 'connectorCategoryUnknown', 'connectorCategoryUnknownHint'],
  ])('words the category %s with %s and %s', (category, labelKey, hintKey) => {
    expect(connectorCategoryLabelKey(category)).toBe(labelKey);
    expect(connectorCategoryHintKey(category)).toBe(hintKey);
  });

  // A category with no wording of its own reads as unknown: an empty one, one the server does not record
  // (`process_error`), and the names every object inherits.
  it.each(['', 'process_error', 'made-up-category', 'constructor', 'toString', '__proto__'])(
    'reads %j as unknown',
    (category) => {
      expect(connectorCategoryLabelKey(category)).toBe('connectorCategoryUnknown');
      expect(connectorCategoryHintKey(category)).toBe('connectorCategoryUnknownHint');
    },
  );
});

describe('isFailedRunStatus', () => {
  it.each([
    ['error', true],
    ['circuit_break', true],
    ['skipped', false],
    ['ok', false],
    [undefined, false],
  ] as const)('reads the run status %s as failed: %s', (status, failed) => {
    expect(isFailedRunStatus(status)).toBe(failed);
  });
});

describe('isFailingJob', () => {
  it.each([
    ['a failure streak', { consecutive_failures: 2 }, true],
    ['an error as the last run', { last_status: 'error' }, true],
    ['a loop-guard break after a resume reset the streak', { last_status: 'circuit_break' }, true],
    ['a skipped last run', { last_status: 'skipped' }, false],
    ['a successful last run', { last_status: 'ok' }, false],
    ['no run yet', {}, false],
  ] satisfies Array<[string, Partial<CronJob>, boolean]>)('reads %s as failing: %s', (_case, fields, failing) => {
    expect(isFailingJob(makeJob(fields))).toBe(failing);
  });

  describe('is the one verdict behind every job-list view', () => {
    const broken = makeJob({ id: 'broken', last_status: 'circuit_break' });
    const healthy = makeJob({ id: 'healthy', last_status: 'ok' });

    it('counts the job as errored', () => {
      expect(computeStats([broken, healthy]).errored).toBe(1);
    });

    it('lists it under the error filter', () => {
      expect(filterJobs([broken, healthy], 'error', '').map((job) => job.id)).toEqual(['broken']);
    });

    it('draws its card border as a failure', () => {
      expect(statusBorderColor(broken)).toBe('border-l-destructive');
      expect(statusBorderColor(healthy)).not.toBe('border-l-destructive');
    });
  });
});

describe('runStatusLabelKey', () => {
  it.each([
    ['ok', 'runOk'],
    ['error', 'runError'],
    ['skipped', 'runSkipped'],
    ['circuit_break', 'runCircuitBreak'],
  ] satisfies Array<[RunStatus, string]>)('words the status %s with %s', (status, labelKey) => {
    expect(runStatusLabelKey(status)).toBe(labelKey);
  });
});

describe('pauseReasonLabelKey', () => {
  it.each([
    ['circuit_break', 'circuitBreakBanner'],
    ['run_failures', 'pausedRunFailures'],
    ['schedule_error', 'pausedScheduleError'],
  ] satisfies Array<[PauseReason, string]>)('words the pause reason %s with %s', (reason, labelKey) => {
    expect(pauseReasonLabelKey(reason)).toBe(labelKey);
  });
});