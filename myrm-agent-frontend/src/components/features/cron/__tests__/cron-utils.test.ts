import { describe, expect, it, vi } from 'vitest';
import { CRON_OVERDUE_THRESHOLD_MS, formatRelativeTime, isCronOverdue } from '../cron-utils';
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
    if (key === 'relativeDate.justNow') {return 'just now';}
    if (key === 'relativeDate.minutesAgo') {return `${values?.count}m ago`;}
    if (key === 'relativeDate.hoursAgo') {return `${values?.count}h ago`;}
    if (key === 'relativeDate.daysAgo') {return `${values?.count}d ago`;}
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
    const expected = new Intl.DateTimeFormat(locale, { month: 'short', day: 'numeric' }).format(
      now - 10 * 86_400_000,
    );
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