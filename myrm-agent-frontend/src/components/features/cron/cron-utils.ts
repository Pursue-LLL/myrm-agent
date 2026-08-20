import type { CronJob, CronRun, JobStatus } from '@/services/cron';

const SYSTEM_JOB_PREFIX = '__';

export function isSystemJob(job: CronJob): boolean {
  return job.name.startsWith(SYSTEM_JOB_PREFIX);
}

export type StatusFilter = 'all' | 'active' | 'paused' | 'error';

export const STATUS_BADGE_STYLE: Record<JobStatus, string> = {
  active: 'bg-green-500/10 text-green-600 dark:text-green-400 border-green-500/20',
  paused: 'bg-muted text-muted-foreground border-muted',
  completed: 'bg-blue-500/10 text-blue-600 dark:text-blue-400 border-blue-500/20',
};

export const STATUS_DOT_COLOR: Record<JobStatus, string> = {
  active: 'bg-green-500',
  paused: 'bg-muted-foreground/50',
  completed: 'bg-blue-500',
};

export function formatNextRun(
  nextRunAt: string | undefined,
  t: (key: string, values?: Record<string, string>) => string,
): string {
  if (!nextRunAt) {
    return '—';
  }
  const diffMs = new Date(nextRunAt).getTime() - Date.now();
  if (diffMs < 0) {
    return t('overdue');
  }
  if (diffMs < 60_000) {
    return t('timeSeconds', { value: String(Math.round(diffMs / 1000)) });
  }
  if (diffMs < 3_600_000) {
    return t('timeMinutes', { value: String(Math.round(diffMs / 60_000)) });
  }
  if (diffMs < 86_400_000) {
    return t('timeHours', { value: String(Math.round(diffMs / 3_600_000)) });
  }
  return t('timeDays', { value: String(Math.round(diffMs / 86_400_000)) });
}

export function formatDuration(ms: number): string {
  if (ms < 1000) {
    return `${ms}ms`;
  }
  if (ms < 60_000) {
    return `${(ms / 1000).toFixed(1)}s`;
  }
  return `${(ms / 60_000).toFixed(1)}m`;
}

export function formatTime(iso: string, locale: string): string {
  return new Intl.DateTimeFormat(locale, {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(new Date(iso));
}

/** Render an ISO timestamp as a compact, localized relative time (e.g. "3h ago").
 *
 * Uses the shared common.relativeDate keys. Falls back to a short month/day
 * date after a week to avoid meaningless "999d ago" noise in list summaries.
 */
export function formatRelativeTime(
  iso: string,
  t: (key: string, values?: Record<string, number>) => string,
  locale: string,
  nowMs = Date.now(),
): string {
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) {
    return '';
  }
  const diffMs = nowMs - then;
  const minutes = Math.floor(diffMs / 60_000);
  if (minutes < 1) {
    return t('relativeDate.justNow');
  }
  if (minutes < 60) {
    return t('relativeDate.minutesAgo', { count: minutes });
  }
  const hours = Math.floor(diffMs / 3_600_000);
  if (hours < 24) {
    return t('relativeDate.hoursAgo', { count: hours });
  }
  const days = Math.floor(diffMs / 86_400_000);
  if (days < 7) {
    return t('relativeDate.daysAgo', { count: days });
  }
  return new Intl.DateTimeFormat(locale, { month: 'short', day: 'numeric' }).format(then);
}

export function statusBorderColor(job: CronJob): string {
  if (job.consecutive_failures > 0 || job.last_status === 'error') {
    return 'border-l-destructive';
  }
  if (job.status === 'active') {
    return 'border-l-green-500';
  }
  return 'border-l-muted-foreground/40';
}

/**
 * A recurring active job is considered overdue only after this base margin, so the
 * alert never fires within the scheduler's normal tick latency. The effective
 * threshold is `max(misfire_grace_seconds, BASE_MARGIN)` — see isCronOverdue.
 */
export const CRON_OVERDUE_THRESHOLD_MS = 10 * 60_000;

/**
 * True when an active recurring job missed its scheduled slot.
 *
 * While the server runs, its scheduler keeps ticking (watchdog ≤ 30s) and claims due
 * jobs almost immediately, so an overdue window mainly appears when the scheduler is
 * not running — host asleep, service closed, or the server is otherwise unavailable.
 *
 * The effective threshold is the larger of the job's `misfire_grace_seconds` and the
 * base `CRON_OVERDUE_THRESHOLD_MS` margin. Tying it to the configured grace keeps the
 * alert in sync with the backend `is_past_misfire_grace` (a job inside its grace window
 * is still replayable on startup recovery, so it must not be reported as missed);
 * the base margin keeps the alert from firing during normal tick latency.
 * One-time jobs are excluded because they have no recurring expectation.
 */
export function isCronOverdue(job: CronJob, nowMs = Date.now()): boolean {
  if (job.status !== 'active') {
    return false;
  }
  if (job.schedule?.kind === 'once') {
    return false;
  }
  if (!job.next_run_at) {
    return false;
  }
  const graceMs = Math.max(job.misfire_grace_seconds, 0) * 1000;
  const thresholdMs = Math.max(graceMs, CRON_OVERDUE_THRESHOLD_MS);
  return nowMs - new Date(job.next_run_at).getTime() > thresholdMs;
}

export function computeStats(jobs: CronJob[]) {
  const userJobs = jobs.filter((j) => !isSystemJob(j));
  let active = 0;
  let paused = 0;
  let errored = 0;
  for (const j of userJobs) {
    if (j.status === 'active') {
      active++;
    } else if (j.status === 'paused') {
      paused++;
    }
    if (j.last_status === 'error' || j.consecutive_failures > 0) {
      errored++;
    }
  }
  return { total: userJobs.length, active, paused, errored };
}

export function filterJobs(jobs: CronJob[], filter: StatusFilter, query: string): CronJob[] {
  let result = jobs.filter((j) => !isSystemJob(j));
  if (filter === 'active') {
    result = result.filter((j) => j.status === 'active');
  } else if (filter === 'paused') {
    result = result.filter((j) => j.status === 'paused');
  } else if (filter === 'error') {
    result = result.filter((j) => j.last_status === 'error' || j.consecutive_failures > 0);
  }
  if (query) {
    const q = query.toLowerCase();
    result = result.filter((j) => j.name.toLowerCase().includes(q) || j.prompt?.toLowerCase().includes(q));
  }
  return result;
}

export function computeRunStats(runs: CronRun[]) {
  if (runs.length === 0) {
    return { total: 0, successRate: 0, avgDuration: 0 };
  }
  const ok = runs.filter((r) => r.status === 'ok').length;
  const avgMs = runs.reduce((sum, r) => sum + r.duration_ms, 0) / runs.length;
  return {
    total: runs.length,
    successRate: Math.round((ok / runs.length) * 100),
    avgDuration: avgMs,
  };
}
