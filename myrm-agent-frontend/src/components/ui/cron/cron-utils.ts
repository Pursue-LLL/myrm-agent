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
  if (!nextRunAt) return '—';
  const diffMs = new Date(nextRunAt).getTime() - Date.now();
  if (diffMs < 0) return t('overdue');
  if (diffMs < 60_000) return t('timeSeconds', { value: String(Math.round(diffMs / 1000)) });
  if (diffMs < 3_600_000) return t('timeMinutes', { value: String(Math.round(diffMs / 60_000)) });
  if (diffMs < 86_400_000) return t('timeHours', { value: String(Math.round(diffMs / 3_600_000)) });
  return t('timeDays', { value: String(Math.round(diffMs / 86_400_000)) });
}

export function formatDuration(ms: number): string {
  if (ms < 1000) return `${ms}ms`;
  if (ms < 60_000) return `${(ms / 1000).toFixed(1)}s`;
  return `${(ms / 60_000).toFixed(1)}m`;
}

export function formatTime(iso: string): string {
  return new Date(iso).toLocaleString();
}

export function statusBorderColor(job: CronJob): string {
  if (job.consecutive_failures > 0 || job.last_status === 'error') return 'border-l-destructive';
  if (job.status === 'active') return 'border-l-green-500';
  return 'border-l-muted-foreground/40';
}

export function computeStats(jobs: CronJob[]) {
  const userJobs = jobs.filter((j) => !isSystemJob(j));
  let active = 0;
  let paused = 0;
  let errored = 0;
  for (const j of userJobs) {
    if (j.status === 'active') active++;
    else if (j.status === 'paused') paused++;
    if (j.last_status === 'error' || j.consecutive_failures > 0) errored++;
  }
  return { total: userJobs.length, active, paused, errored };
}

export function filterJobs(jobs: CronJob[], filter: StatusFilter, query: string): CronJob[] {
  let result = jobs.filter((j) => !isSystemJob(j));
  if (filter === 'active') result = result.filter((j) => j.status === 'active');
  else if (filter === 'paused') result = result.filter((j) => j.status === 'paused');
  else if (filter === 'error') result = result.filter((j) => j.last_status === 'error' || j.consecutive_failures > 0);
  if (query) {
    const q = query.toLowerCase();
    result = result.filter((j) => j.name.toLowerCase().includes(q) || j.prompt?.toLowerCase().includes(q));
  }
  return result;
}

export function computeRunStats(runs: CronRun[]) {
  if (runs.length === 0) return { total: 0, successRate: 0, avgDuration: 0 };
  const ok = runs.filter((r) => r.status === 'ok').length;
  const avgMs = runs.reduce((sum, r) => sum + r.duration_ms, 0) / runs.length;
  return {
    total: runs.length,
    successRate: Math.round((ok / runs.length) * 100),
    avgDuration: avgMs,
  };
}
