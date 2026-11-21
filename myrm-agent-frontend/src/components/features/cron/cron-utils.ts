import type { CronJob, CronRun, JobStatus, PauseReason, RunStatus } from '@/services/cron';

/** The stored name of the heartbeat, the one system job the application creates itself: the user never chose it. */
export const HEARTBEAT_JOB_NAME = '__heartbeat__';

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

/** Pill-shaped item of a single-select toggle group (job type and delivery channel pickers). */
export const PILL_TOGGLE_CLASS =
  'gap-1.5 text-xs h-8 px-3 rounded-full border border-border bg-muted/50 data-[state=on]:bg-primary/10 data-[state=on]:text-primary data-[state=on]:border-primary/40';

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

export type SkipReasonLabelKey =
  | 'skippedUsageLimit'
  | 'skippedBudgetBlocked'
  | 'skippedCreditExhausted'
  | 'skippedPreflight'
  | 'skippedNoContent'
  | 'skippedCooldown'
  | 'skippedOutsideHours'
  | 'skippedUntrustedWorkflow'
  | 'skippedMemoryPressure';

/**
 * Codes the server records as the output of a skipped run, each with the label that explains it.
 * A `Map`, because an object lookup would treat `constructor` or `toString` as a known code.
 */
const SKIP_REASON_LABEL_KEYS = new Map<string, SkipReasonLabelKey>([
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
]);

/** The label key for a skipped run's output, or `undefined` when the output is not a code with a label. */
export function skipReasonLabelKey(output: string | undefined): SkipReasonLabelKey | undefined {
  return output ? SKIP_REASON_LABEL_KEYS.get(output) : undefined;
}

export type TriggerSourceLabelKey =
  | 'triggerSourceCron'
  | 'triggerSourceEvent'
  | 'triggerSourceWebhook'
  | 'triggerSourceSystem'
  | 'triggerSourceManual'
  | 'triggerSourceRecovery'
  | 'triggerSourceShutdown';

/** What the server records as the source of a run, each with the label that names it (a `Map` for the reason above). */
const TRIGGER_SOURCE_LABEL_KEYS = new Map<string, TriggerSourceLabelKey>([
  ['cron', 'triggerSourceCron'],
  ['event', 'triggerSourceEvent'],
  ['webhook', 'triggerSourceWebhook'],
  ['system_event', 'triggerSourceSystem'],
  ['manual', 'triggerSourceManual'],
  ['recovery', 'triggerSourceRecovery'],
  ['shutdown', 'triggerSourceShutdown'],
]);

/** The label key for a run's source, or `undefined` when the source is not one the server is known to record. */
export function triggerSourceLabelKey(source: string): TriggerSourceLabelKey | undefined {
  return TRIGGER_SOURCE_LABEL_KEYS.get(source);
}

export type ConnectorCategoryLabelKey =
  | 'connectorCategoryAuth'
  | 'connectorCategoryClient'
  | 'connectorCategoryServer'
  | 'connectorCategoryTimeout'
  | 'connectorCategoryNetwork'
  | 'connectorCategoryPayload'
  | 'connectorCategoryAddress'
  | 'connectorCategoryUnknown';

export type ConnectorCategoryHintKey =
  | 'connectorCategoryAuthHint'
  | 'connectorCategoryClientHint'
  | 'connectorCategoryServerHint'
  | 'connectorCategoryTimeoutHint'
  | 'connectorCategoryNetworkHint'
  | 'connectorCategoryPayloadHint'
  | 'connectorCategoryAddressHint'
  | 'connectorCategoryUnknownHint';

interface ConnectorCategoryWords {
  /** Names what went wrong in plain words. */
  label: ConnectorCategoryLabelKey;
  /** Says what the user can do about it. */
  hint: ConnectorCategoryHintKey;
}

const UNKNOWN_CONNECTOR_CATEGORY: ConnectorCategoryWords = {
  label: 'connectorCategoryUnknown',
  hint: 'connectorCategoryUnknownHint',
};

/** What the server classifies a failed delivery as, each with the words for it (a `Map` for the reason above). */
const CONNECTOR_CATEGORY_WORDS = new Map<string, ConnectorCategoryWords>([
  ['auth_failure', { label: 'connectorCategoryAuth', hint: 'connectorCategoryAuthHint' }],
  ['http_client_error', { label: 'connectorCategoryClient', hint: 'connectorCategoryClientHint' }],
  ['http_server_error', { label: 'connectorCategoryServer', hint: 'connectorCategoryServerHint' }],
  ['timeout', { label: 'connectorCategoryTimeout', hint: 'connectorCategoryTimeoutHint' }],
  ['network_unreachable', { label: 'connectorCategoryNetwork', hint: 'connectorCategoryNetworkHint' }],
  ['payload_contract', { label: 'connectorCategoryPayload', hint: 'connectorCategoryPayloadHint' }],
  ['address_rejected', { label: 'connectorCategoryAddress', hint: 'connectorCategoryAddressHint' }],
  ['unknown', UNKNOWN_CONNECTOR_CATEGORY],
]);

/** The label key for a failed delivery's category; a category the server is not known to record reads as unknown. */
export function connectorCategoryLabelKey(category: string): ConnectorCategoryLabelKey {
  return (CONNECTOR_CATEGORY_WORDS.get(category) ?? UNKNOWN_CONNECTOR_CATEGORY).label;
}

/** The key of what to do about a failed delivery's category; an unknown category points at the run's details. */
export function connectorCategoryHintKey(category: string): ConnectorCategoryHintKey {
  return (CONNECTOR_CATEGORY_WORDS.get(category) ?? UNKNOWN_CONNECTOR_CATEGORY).hint;
}

/** What the server accepts for a job's run time limit, in whole seconds. */
export const CRON_TIMEOUT_MIN_SECONDS = 10;
export const CRON_TIMEOUT_MAX_SECONDS = 3600;
export const CRON_TIMEOUT_DEFAULT_SECONDS = 300;

/** The limit the user typed, or null when it is empty, not a whole number or outside the accepted range. */
export function parseTimeoutSeconds(raw: string): number | null {
  const trimmed = raw.trim();
  if (!/^\d+$/.test(trimmed)) {
    return null;
  }
  const seconds = Number(trimmed);
  return seconds >= CRON_TIMEOUT_MIN_SECONDS && seconds <= CRON_TIMEOUT_MAX_SECONDS ? seconds : null;
}

/** A run time limit as `1h 5m 30s`, leaving out the zero parts. */
export function formatTimeoutSeconds(seconds: number): string {
  const parts: Array<[number, string]> = [
    [Math.floor(seconds / 3600), 'h'],
    [Math.floor((seconds % 3600) / 60), 'm'],
    [seconds % 60, 's'],
  ];
  const text = parts
    .filter(([amount]) => amount > 0)
    .map(([amount, unit]) => `${amount}${unit}`)
    .join(' ');
  return text || '0s';
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

// The run statuses that count as a failure, as the server counts them: an error and a loop-guard break.
const FAILED_RUN_STATUSES: ReadonlySet<RunStatus> = new Set<RunStatus>(['error', 'circuit_break']);

export function isFailedRunStatus(status: RunStatus | undefined): boolean {
  return status !== undefined && FAILED_RUN_STATUSES.has(status);
}

/** A job that needs the user's eye: its last run failed, or it is on a failure streak. */
export function isFailingJob(job: CronJob): boolean {
  return job.consecutive_failures > 0 || isFailedRunStatus(job.last_status);
}

export type RunStatusLabelKey = 'runOk' | 'runError' | 'runSkipped' | 'runCircuitBreak';

/** The word for each run status; a circuit break has its own, not the plain error's. */
const RUN_STATUS_LABEL_KEYS: Record<RunStatus, RunStatusLabelKey> = {
  ok: 'runOk',
  error: 'runError',
  skipped: 'runSkipped',
  circuit_break: 'runCircuitBreak',
};

export function runStatusLabelKey(status: RunStatus): RunStatusLabelKey {
  return RUN_STATUS_LABEL_KEYS[status];
}

export type PauseReasonLabelKey = 'circuitBreakBanner' | 'pausedRunFailures' | 'pausedScheduleError';

/** The sentence for why the scheduler paused a job by itself; a loop-guard break reads as the run's own banner does. */
const PAUSE_REASON_LABEL_KEYS: Record<PauseReason, PauseReasonLabelKey> = {
  circuit_break: 'circuitBreakBanner',
  run_failures: 'pausedRunFailures',
  schedule_error: 'pausedScheduleError',
};

export function pauseReasonLabelKey(reason: PauseReason): PauseReasonLabelKey {
  return PAUSE_REASON_LABEL_KEYS[reason];
}

export function statusBorderColor(job: CronJob): string {
  if (isFailingJob(job)) {
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
  let active = 0;
  let paused = 0;
  let errored = 0;
  for (const j of jobs) {
    if (j.status === 'active') {
      active++;
    } else if (j.status === 'paused') {
      paused++;
    }
    if (isFailingJob(j)) {
      errored++;
    }
  }
  return { total: jobs.length, active, paused, errored };
}

export function filterJobs(jobs: CronJob[], filter: StatusFilter, query: string): CronJob[] {
  let result = jobs;
  if (filter === 'active') {
    result = result.filter((j) => j.status === 'active');
  } else if (filter === 'paused') {
    result = result.filter((j) => j.status === 'paused');
  } else if (filter === 'error') {
    result = result.filter(isFailingJob);
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
