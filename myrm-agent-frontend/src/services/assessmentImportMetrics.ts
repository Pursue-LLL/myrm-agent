/**
 * [INPUT]
 * - @/lib/api::apiRequest (POS: 前端 API 接入层。统一封装请求基址、超时、错误归一化。)
 *
 * [OUTPUT]
 * - recordAssessmentImport*: 评估导入漏斗事件写入。
 * - getAssessmentImportSummary: 评估导入漏斗聚合查询。
 * - getAssessmentImportValueSummary: 导入后价值锚点查询（任务/里程碑完成率）。
 *
 * [POS]
 * 项目里程碑评估导入可观测客户端。负责 attempt/success/failure 事件上报与离线丢样回补，
 * 并提供导入后执行价值锚点查询。
 */
import { apiRequest } from '@/lib/api';

export type AssessmentImportMetricSurface = 'project_milestone_panel';
export type AssessmentImportMetricTrigger = 'manual_input' | 'recent_candidate';
export type AssessmentImportMetricEventType =
  | 'import_attempted'
  | 'import_succeeded'
  | 'import_failed'
  | 'dropped_report';
export type AssessmentImportFailureReason =
  | 'artifact_version_already_imported'
  | 'no_actionable_tasks'
  | 'no_importable_tasks'
  | 'artifact_not_found'
  | 'project_not_found'
  | 'network_error'
  | 'unknown_error';

interface AssessmentImportMetricEventPayload {
  event_type: AssessmentImportMetricEventType;
  surface: AssessmentImportMetricSurface;
  trigger: AssessmentImportMetricTrigger;
  context_key?: string;
  failure_reason?: AssessmentImportFailureReason;
  count?: number;
}

interface AssessmentImportMetricEventOptions {
  contextKey?: string;
  surface?: AssessmentImportMetricSurface;
}

export interface AssessmentImportSummary {
  days: number;
  retention_days: number;
  total_events: number;
  import_attempted_count: number;
  import_succeeded_count: number;
  import_failed_count: number;
  dropped_event_count: number;
  success_rate: number;
  failure_rate: number;
  recent_candidate_attempt_rate: number;
  attempts_by_trigger: Record<AssessmentImportMetricTrigger, number>;
  successes_by_trigger: Record<AssessmentImportMetricTrigger, number>;
  failures_by_trigger: Record<AssessmentImportMetricTrigger, number>;
  failure_reason_breakdown: Record<string, number>;
}

export interface AssessmentImportValueSummary {
  days: number;
  project_id: string | null;
  imports_total: number;
  imports_with_task_completion: number;
  imports_with_milestone_completion: number;
  imported_tasks_total: number;
  completed_tasks_total: number;
  imported_milestones_total: number;
  completed_milestones_total: number;
  task_completion_rate: number;
  milestone_completion_rate: number;
  import_activation_rate: number;
}

const MAX_EVENT_COUNT = 200;
const MAX_PENDING_DROPPED_EVENTS = 1_000;
const DEFAULT_CONTEXT_KEY = 'global';
const DEFAULT_SURFACE: AssessmentImportMetricSurface = 'project_milestone_panel';
const DROPPED_BUFFER_STORAGE_KEY = 'assessmentImportDroppedBufferV1';
const IMPORT_TRIGGERS: AssessmentImportMetricTrigger[] = ['manual_input', 'recent_candidate'];

let pendingDroppedEventsByTrigger = loadDroppedBufferFromStorage();
let postQueue: Promise<void> = Promise.resolve();

function normalizeContextKey(contextKey?: string): string {
  const normalized = contextKey?.trim();
  return normalized && normalized.length > 0 ? normalized : DEFAULT_CONTEXT_KEY;
}

function clampCount(count: number): number {
  if (!Number.isFinite(count)) return 1;
  return Math.max(1, Math.min(MAX_EVENT_COUNT, Math.floor(count)));
}

function totalPendingDroppedEvents(): number {
  return IMPORT_TRIGGERS.reduce((sum, trigger) => sum + pendingDroppedEventsByTrigger[trigger], 0);
}

function createEmptyDroppedBuffer(): Record<AssessmentImportMetricTrigger, number> {
  return {
    manual_input: 0,
    recent_candidate: 0,
  };
}

function clampPendingCount(count: number | undefined): number {
  if (!Number.isFinite(count)) {
    return 0;
  }
  return Math.max(0, Math.min(MAX_PENDING_DROPPED_EVENTS, Math.floor(count)));
}

function loadDroppedBufferFromStorage(): Record<AssessmentImportMetricTrigger, number> {
  if (typeof window === 'undefined') {
    return createEmptyDroppedBuffer();
  }
  try {
    const raw = window.localStorage.getItem(DROPPED_BUFFER_STORAGE_KEY);
    if (!raw) {
      return createEmptyDroppedBuffer();
    }
    const parsed = JSON.parse(raw) as Partial<Record<AssessmentImportMetricTrigger, number>>;
    return {
      manual_input: clampPendingCount(parsed.manual_input),
      recent_candidate: clampPendingCount(parsed.recent_candidate),
    };
  } catch {
    return createEmptyDroppedBuffer();
  }
}

function persistDroppedBufferToStorage(): void {
  if (typeof window === 'undefined') {
    return;
  }
  try {
    if (totalPendingDroppedEvents() <= 0) {
      window.localStorage.removeItem(DROPPED_BUFFER_STORAGE_KEY);
      return;
    }
    window.localStorage.setItem(DROPPED_BUFFER_STORAGE_KEY, JSON.stringify(pendingDroppedEventsByTrigger));
  } catch {
    // Local storage failures should never block telemetry.
  }
}

function addPendingDroppedEvents(trigger: AssessmentImportMetricTrigger, increment: number): void {
  const remainingCapacity = Math.max(0, MAX_PENDING_DROPPED_EVENTS - totalPendingDroppedEvents());
  if (remainingCapacity <= 0) {
    return;
  }
  pendingDroppedEventsByTrigger[trigger] += Math.min(remainingCapacity, clampCount(increment));
  persistDroppedBufferToStorage();
}

async function postAssessmentImportEvent(
  payload: AssessmentImportMetricEventPayload,
  countAsDropped: boolean = true,
): Promise<boolean> {
  try {
    await apiRequest('/statistics/assessment-import/events', {
      method: 'POST',
      body: JSON.stringify(payload),
      silent: true,
    });
    return true;
  } catch {
    if (countAsDropped && payload.event_type !== 'dropped_report') {
      addPendingDroppedEvents(payload.trigger, payload.count ?? 1);
    }
    return false;
  }
}

async function flushDroppedEvents(surface: AssessmentImportMetricSurface): Promise<void> {
  if (totalPendingDroppedEvents() <= 0) {
    return;
  }
  let changed = false;
  for (const trigger of IMPORT_TRIGGERS) {
    const droppedCount = pendingDroppedEventsByTrigger[trigger];
    if (droppedCount <= 0) {
      continue;
    }
    pendingDroppedEventsByTrigger[trigger] = 0;
    changed = true;
    const flushed = await postAssessmentImportEvent(
      {
        event_type: 'dropped_report',
        surface,
        trigger,
        context_key: DEFAULT_CONTEXT_KEY,
        count: droppedCount,
      },
      false,
    );
    if (!flushed) {
      addPendingDroppedEvents(trigger, droppedCount);
    }
  }
  if (changed) {
    persistDroppedBufferToStorage();
  }
}

function enqueueAssessmentImportEvent(payload: AssessmentImportMetricEventPayload): void {
  postQueue = postQueue
    .then(async () => {
      const posted = await postAssessmentImportEvent(payload);
      if (posted) {
        await flushDroppedEvents(payload.surface);
      }
    })
    .catch(() => {
      // Keep queue alive after unexpected runtime errors.
    });
}

function buildPayload(
  eventType: AssessmentImportMetricEventType,
  trigger: AssessmentImportMetricTrigger,
  options?: AssessmentImportMetricEventOptions,
  failureReason?: AssessmentImportFailureReason,
): AssessmentImportMetricEventPayload {
  const surface = options?.surface ?? DEFAULT_SURFACE;
  const contextKey = normalizeContextKey(options?.contextKey);
  return {
    event_type: eventType,
    surface,
    trigger,
    context_key: contextKey,
    count: 1,
    failure_reason: failureReason,
  };
}

export function recordAssessmentImportAttempted(
  trigger: AssessmentImportMetricTrigger,
  options?: AssessmentImportMetricEventOptions,
): void {
  const payload = buildPayload('import_attempted', trigger, options);
  enqueueAssessmentImportEvent(payload);
}

export function recordAssessmentImportSucceeded(
  trigger: AssessmentImportMetricTrigger,
  options?: AssessmentImportMetricEventOptions,
): void {
  const payload = buildPayload('import_succeeded', trigger, options);
  enqueueAssessmentImportEvent(payload);
}

export function recordAssessmentImportFailed(
  trigger: AssessmentImportMetricTrigger,
  failureReason: AssessmentImportFailureReason,
  options?: AssessmentImportMetricEventOptions,
): void {
  const payload = buildPayload('import_failed', trigger, options, failureReason);
  enqueueAssessmentImportEvent(payload);
}

export async function getAssessmentImportSummary(days: number = 30): Promise<AssessmentImportSummary> {
  const normalizedDays = Math.max(1, Math.min(90, Math.floor(days)));
  return (await apiRequest(`/statistics/assessment-import/summary?days=${normalizedDays}`)) as AssessmentImportSummary;
}

export async function getAssessmentImportValueSummary(
  days: number = 30,
  projectId?: string,
): Promise<AssessmentImportValueSummary> {
  const normalizedDays = Math.max(1, Math.min(90, Math.floor(days)));
  const query = new URLSearchParams({ days: String(normalizedDays) });
  const normalizedProjectId = projectId?.trim();
  if (normalizedProjectId) {
    query.set('project_id', normalizedProjectId);
  }
  return (await apiRequest(`/statistics/assessment-import/value-summary?${query.toString()}`)) as AssessmentImportValueSummary;
}

export async function __flushAssessmentImportMetricsForTest(): Promise<void> {
  await postQueue;
}

export function __resetAssessmentImportMetricsForTest(): void {
  pendingDroppedEventsByTrigger = createEmptyDroppedBuffer();
  postQueue = Promise.resolve();
  if (typeof window !== 'undefined') {
    try {
      window.localStorage.removeItem(DROPPED_BUFFER_STORAGE_KEY);
    } catch {
      // no-op
    }
  }
}
