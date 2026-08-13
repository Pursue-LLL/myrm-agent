/**
 * [INPUT]
 * - @/lib/api::apiRequest (POS: 前端 API 接入层。统一封装请求基址、超时、错误归一化与安全拦截。)
 *
 * [OUTPUT]
 * - recordTurnCapability*: 单轮 Skill/MCP 覆写链路观测事件写入。
 * - getTurnCapabilitySummary: 单轮覆写观测聚合查询。
 *
 * [POS]
 * 单轮能力覆写可观测客户端。负责 direct/queue 发送路径的埋点上报与离线丢样回补。
 */
import { apiRequest } from '@/lib/api';

export type TurnCapabilityMetricSource = 'direct' | 'queue_submit' | 'queue_drain' | 'busy_requeue';
export type TurnCapabilityMetricEventType =
  | 'selection_submitted'
  | 'override_applied'
  | 'override_noop'
  | 'queue_enqueued'
  | 'send_completed'
  | 'send_failed'
  | 'busy_requeued'
  | 'dropped_report';
export type TurnCapabilityFailureReason =
  | 'network_error'
  | 'archive_restore_invalid'
  | 'abort'
  | 'server_error'
  | 'unknown_error';

interface TurnCapabilityMetricEventPayload {
  event_type: TurnCapabilityMetricEventType;
  source: TurnCapabilityMetricSource;
  context_key?: string;
  count?: number;
  selected_skill_count?: number;
  selected_mcp_count?: number;
  effective_skill_count?: number;
  effective_mcp_count?: number;
  failure_reason?: TurnCapabilityFailureReason;
}

export interface TurnCapabilitySummary {
  days: number;
  retention_days: number;
  total_events: number;
  selection_submitted_count: number;
  override_applied_count: number;
  override_noop_count: number;
  queue_enqueued_count: number;
  send_completed_count: number;
  send_failed_count: number;
  busy_requeued_count: number;
  dropped_event_count: number;
  apply_rate: number;
  noop_rate: number;
  queue_rate: number;
  completion_rate: number;
  failure_rate: number;
  avg_selected_skill_count: number;
  avg_selected_mcp_count: number;
  avg_effective_skill_count: number;
  avg_effective_mcp_count: number;
  submitted_by_source: Record<TurnCapabilityMetricSource, number>;
  applied_by_source: Record<TurnCapabilityMetricSource, number>;
  completed_by_source: Record<TurnCapabilityMetricSource, number>;
  failed_by_source: Record<TurnCapabilityMetricSource, number>;
  failure_reason_breakdown: Record<string, number>;
}

const MAX_EVENT_COUNT = 200;
const MAX_PENDING_DROPPED_EVENTS = 1_000;
const DEFAULT_CONTEXT_KEY = 'global';
const DROPPED_BUFFER_STORAGE_KEY = 'turnCapabilityDroppedBufferV1';
const TURN_CAPABILITY_SOURCES: TurnCapabilityMetricSource[] = ['direct', 'queue_submit', 'queue_drain', 'busy_requeue'];

let pendingDroppedEventsBySource = loadDroppedBufferFromStorage();
let postQueue: Promise<void> = Promise.resolve();

function normalizeContextKey(contextKey?: string): string {
  const normalized = contextKey?.trim();
  return normalized && normalized.length > 0 ? normalized : DEFAULT_CONTEXT_KEY;
}

function clampCount(count: number): number {
  if (!Number.isFinite(count)) {return 1;}
  return Math.max(1, Math.min(MAX_EVENT_COUNT, Math.floor(count)));
}

function clampMetricCount(value: number | undefined): number | undefined {
  if (value === undefined || !Number.isFinite(value)) {
    return undefined;
  }
  return Math.max(0, Math.min(500, Math.floor(value)));
}

async function postTurnCapabilityEvent(
  payload: TurnCapabilityMetricEventPayload,
  countAsDropped: boolean = true,
): Promise<boolean> {
  try {
    await apiRequest('/statistics/turn-capability/events', {
      method: 'POST',
      body: JSON.stringify(payload),
      silent: true,
    });
    return true;
  } catch {
    if (countAsDropped && payload.event_type !== 'dropped_report') {
      addPendingDroppedEvents(payload.source, payload.count ?? 1);
    }
    return false;
  }
}

async function flushDroppedEvents(contextKey: string): Promise<void> {
  if (totalPendingDroppedEvents() <= 0) {
    return;
  }
  let changed = false;
  for (const source of TURN_CAPABILITY_SOURCES) {
    const droppedCount = pendingDroppedEventsBySource[source];
    if (droppedCount <= 0) {
      continue;
    }
    pendingDroppedEventsBySource[source] = 0;
    changed = true;
    const flushed = await postTurnCapabilityEvent(
      {
        event_type: 'dropped_report',
        source,
        context_key: contextKey,
        count: droppedCount,
      },
      false,
    );

    if (!flushed) {
      addPendingDroppedEvents(source, droppedCount);
    }
  }
  if (changed) {
    persistDroppedBufferToStorage();
  }
}

function enqueueTurnCapabilityEvent(payload: TurnCapabilityMetricEventPayload, contextKey: string): void {
  postQueue = postQueue
    .then(async () => {
      const posted = await postTurnCapabilityEvent(payload);
      if (posted) {
        await flushDroppedEvents(contextKey);
      }
    })
    .catch(() => {
      // Keep queue alive after unexpected runtime errors.
    });
}

function totalPendingDroppedEvents(): number {
  return TURN_CAPABILITY_SOURCES.reduce((sum, source) => sum + pendingDroppedEventsBySource[source], 0);
}

function addPendingDroppedEvents(source: TurnCapabilityMetricSource, increment: number): void {
  const remainingCapacity = Math.max(0, MAX_PENDING_DROPPED_EVENTS - totalPendingDroppedEvents());
  if (remainingCapacity <= 0) {
    return;
  }
  pendingDroppedEventsBySource[source] += Math.min(remainingCapacity, clampCount(increment));
  persistDroppedBufferToStorage();
}

function createEmptyDroppedBuffer(): Record<TurnCapabilityMetricSource, number> {
  return {
    direct: 0,
    queue_submit: 0,
    queue_drain: 0,
    busy_requeue: 0,
  };
}

function loadDroppedBufferFromStorage(): Record<TurnCapabilityMetricSource, number> {
  if (typeof window === 'undefined') {
    return createEmptyDroppedBuffer();
  }
  try {
    const raw = window.localStorage.getItem(DROPPED_BUFFER_STORAGE_KEY);
    if (!raw) {
      return createEmptyDroppedBuffer();
    }
    const parsed = JSON.parse(raw) as Partial<Record<TurnCapabilityMetricSource, number>>;
    return {
      direct: clampPendingCount(parsed.direct),
      queue_submit: clampPendingCount(parsed.queue_submit),
      queue_drain: clampPendingCount(parsed.queue_drain),
      busy_requeue: clampPendingCount(parsed.busy_requeue),
    };
  } catch {
    return createEmptyDroppedBuffer();
  }
}

function clampPendingCount(count: number | undefined): number {
  if (count === undefined || !Number.isFinite(count)) {
    return 0;
  }
  return Math.max(0, Math.min(MAX_PENDING_DROPPED_EVENTS, Math.floor(count)));
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
    window.localStorage.setItem(DROPPED_BUFFER_STORAGE_KEY, JSON.stringify(pendingDroppedEventsBySource));
  } catch {
    // Storage failures should never block telemetry.
  }
}

function enqueueSimpleEvent(
  eventType: Exclude<TurnCapabilityMetricEventType, 'dropped_report'>,
  source: TurnCapabilityMetricSource,
  contextKey?: string,
  selectedSkillCount?: number,
  selectedMcpCount?: number,
  effectiveSkillCount?: number,
  effectiveMcpCount?: number,
  failureReason?: TurnCapabilityFailureReason,
): void {
  const normalizedContextKey = normalizeContextKey(contextKey);
  enqueueTurnCapabilityEvent(
    {
      event_type: eventType,
      source,
      context_key: normalizedContextKey,
      count: 1,
      selected_skill_count: clampMetricCount(selectedSkillCount),
      selected_mcp_count: clampMetricCount(selectedMcpCount),
      effective_skill_count: clampMetricCount(effectiveSkillCount),
      effective_mcp_count: clampMetricCount(effectiveMcpCount),
      failure_reason: failureReason,
    },
    normalizedContextKey,
  );
}

export function recordTurnCapabilitySelectionSubmitted(
  source: TurnCapabilityMetricSource,
  selectedSkillCount?: number,
  selectedMcpCount?: number,
  contextKey?: string,
): void {
  enqueueSimpleEvent('selection_submitted', source, contextKey, selectedSkillCount, selectedMcpCount);
}

export function recordTurnCapabilityOverrideApplied(
  source: TurnCapabilityMetricSource,
  selectedSkillCount: number | undefined,
  selectedMcpCount: number | undefined,
  effectiveSkillCount: number,
  effectiveMcpCount: number,
  contextKey?: string,
): void {
  enqueueSimpleEvent(
    'override_applied',
    source,
    contextKey,
    selectedSkillCount,
    selectedMcpCount,
    effectiveSkillCount,
    effectiveMcpCount,
  );
}

export function recordTurnCapabilityOverrideNoop(
  source: TurnCapabilityMetricSource,
  selectedSkillCount?: number,
  selectedMcpCount?: number,
  contextKey?: string,
): void {
  enqueueSimpleEvent('override_noop', source, contextKey, selectedSkillCount, selectedMcpCount);
}

export function recordTurnCapabilityQueueEnqueued(
  source: TurnCapabilityMetricSource,
  selectedSkillCount?: number,
  selectedMcpCount?: number,
  contextKey?: string,
): void {
  enqueueSimpleEvent('queue_enqueued', source, contextKey, selectedSkillCount, selectedMcpCount);
}

export function recordTurnCapabilitySendCompleted(
  source: TurnCapabilityMetricSource,
  effectiveSkillCount: number,
  effectiveMcpCount: number,
  contextKey?: string,
): void {
  enqueueSimpleEvent('send_completed', source, contextKey, undefined, undefined, effectiveSkillCount, effectiveMcpCount);
}

export function recordTurnCapabilitySendFailed(
  source: TurnCapabilityMetricSource,
  failureReason: TurnCapabilityFailureReason,
  contextKey?: string,
): void {
  enqueueSimpleEvent('send_failed', source, contextKey, undefined, undefined, undefined, undefined, failureReason);
}

export function recordTurnCapabilityBusyRequeued(source: TurnCapabilityMetricSource, contextKey?: string): void {
  enqueueSimpleEvent('busy_requeued', source, contextKey);
}

export async function getTurnCapabilitySummary(days: number = 30): Promise<TurnCapabilitySummary> {
  return apiRequest<TurnCapabilitySummary>(`/statistics/turn-capability/summary?days=${days}`);
}

export async function __flushTurnCapabilityMetricsForTest(): Promise<void> {
  await postQueue;
}

export function __resetTurnCapabilityMetricsForTest(): void {
  pendingDroppedEventsBySource = createEmptyDroppedBuffer();
  postQueue = Promise.resolve();
  if (typeof window !== 'undefined') {
    window.localStorage.removeItem(DROPPED_BUFFER_STORAGE_KEY);
  }
}
