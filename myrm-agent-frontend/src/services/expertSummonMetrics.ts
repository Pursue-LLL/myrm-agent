/**
 * [INPUT]
 * - @/lib/api::apiRequest (POS: 前端 API 接入层。统一请求基址、超时、错误归一化。)
 *
 * [OUTPUT]
 * - recordExpertSummon*: 专家召唤漏斗事件写入。
 * - getExpertSummonSummary: 专家召唤漏斗聚合查询。
 *
 * [POS]
 * 专家召唤漏斗可观测客户端。负责 TemplateMarket/FlowPad 的统一埋点口径、
 * 离线丢样聚合回补，以及主路径成功率/失败率/首条发送转化率观测。
 */
import { apiRequest } from '@/lib/api';
import type { ExpertTemplateKind } from '@/services/templateDiscovery';

export type ExpertSummonMetricSurface = 'template_market' | 'flow_pad_inline';
export type ExpertSummonMetricTrigger = 'template_card' | 'use_case_chip' | 'route_menu';
export type ExpertSummonMetricEventType =
  | 'surface_viewed'
  | 'search_used'
  | 'summon_attempted'
  | 'summon_succeeded'
  | 'summon_failed'
  | 'route_applied'
  | 'route_apply_failed'
  | 'first_message_sent'
  | 'dropped_report';
export type ExpertSummonFailureReason =
  | 'network_error'
  | 'route_apply_failed'
  | 'server_error'
  | 'unknown_error';

interface ExpertSummonMetricEventPayload {
  event_type: ExpertSummonMetricEventType;
  surface: ExpertSummonMetricSurface;
  context_key?: string;
  count?: number;
  trigger?: ExpertSummonMetricTrigger;
  template_kind?: ExpertTemplateKind;
  from_search?: boolean;
  used_use_case?: boolean;
  query_length?: number;
  failure_reason?: ExpertSummonFailureReason;
}

export interface ExpertSummonSummary {
  days: number;
  retention_days: number;
  total_events: number;
  surface_viewed_count: number;
  search_used_count: number;
  summon_attempted_count: number;
  summon_succeeded_count: number;
  summon_failed_count: number;
  route_applied_count: number;
  route_apply_failed_count: number;
  first_message_sent_count: number;
  dropped_event_count: number;
  summon_success_rate: number;
  summon_failure_rate: number;
  route_apply_rate: number;
  first_message_sent_rate: number;
  use_case_trigger_rate: number;
  search_assisted_summon_rate: number;
  avg_search_query_length: number;
  viewed_by_surface: Record<ExpertSummonMetricSurface, number>;
  attempted_by_surface: Record<ExpertSummonMetricSurface, number>;
  succeeded_by_surface: Record<ExpertSummonMetricSurface, number>;
  failed_by_surface: Record<ExpertSummonMetricSurface, number>;
  attempted_by_trigger: Record<ExpertSummonMetricTrigger, number>;
  failure_reason_breakdown: Record<string, number>;
}

const MAX_EVENT_COUNT = 200;
const MAX_QUERY_LENGTH = 200;
const MAX_PENDING_DROPPED_EVENTS = 1_000;
const DEFAULT_CONTEXT_KEY = 'global';
const DROPPED_BUFFER_STORAGE_KEY = 'expertSummonDroppedBufferV1';
const SUMMON_SURFACES: ExpertSummonMetricSurface[] = ['template_market', 'flow_pad_inline'];

let pendingDroppedEventsBySurface = loadDroppedBufferFromStorage();
let postQueue: Promise<void> = Promise.resolve();

function clampCount(count: number): number {
  if (!Number.isFinite(count)) {return 1;}
  return Math.max(1, Math.min(MAX_EVENT_COUNT, Math.floor(count)));
}

function clampQueryLength(length: number): number {
  if (!Number.isFinite(length)) {return 0;}
  return Math.max(0, Math.min(MAX_QUERY_LENGTH, Math.floor(length)));
}

function normalizeContextKey(contextKey?: string): string {
  const normalized = contextKey?.trim();
  return normalized && normalized.length > 0 ? normalized : DEFAULT_CONTEXT_KEY;
}

function totalPendingDroppedEvents(): number {
  return SUMMON_SURFACES.reduce((sum, surface) => sum + pendingDroppedEventsBySurface[surface], 0);
}

function createEmptyDroppedBuffer(): Record<ExpertSummonMetricSurface, number> {
  return {
    template_market: 0,
    flow_pad_inline: 0,
  };
}

function clampPendingCount(count: number | undefined): number {
  if (count === undefined || !Number.isFinite(count)) {
    return 0;
  }
  return Math.max(0, Math.min(MAX_PENDING_DROPPED_EVENTS, Math.floor(count)));
}

function loadDroppedBufferFromStorage(): Record<ExpertSummonMetricSurface, number> {
  if (typeof window === 'undefined') {
    return createEmptyDroppedBuffer();
  }
  try {
    const raw = window.localStorage.getItem(DROPPED_BUFFER_STORAGE_KEY);
    if (!raw) {
      return createEmptyDroppedBuffer();
    }
    const parsed = JSON.parse(raw) as Partial<Record<ExpertSummonMetricSurface, number>>;
    return {
      template_market: clampPendingCount(parsed.template_market),
      flow_pad_inline: clampPendingCount(parsed.flow_pad_inline),
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
    window.localStorage.setItem(DROPPED_BUFFER_STORAGE_KEY, JSON.stringify(pendingDroppedEventsBySurface));
  } catch {
    // Storage failures should never block telemetry.
  }
}

function addPendingDroppedEvents(surface: ExpertSummonMetricSurface, increment: number): void {
  const remainingCapacity = Math.max(0, MAX_PENDING_DROPPED_EVENTS - totalPendingDroppedEvents());
  if (remainingCapacity <= 0) {
    return;
  }
  pendingDroppedEventsBySurface[surface] += Math.min(remainingCapacity, clampCount(increment));
  persistDroppedBufferToStorage();
}

async function postExpertSummonEvent(
  payload: ExpertSummonMetricEventPayload,
  countAsDropped: boolean = true,
): Promise<boolean> {
  try {
    await apiRequest('/statistics/expert-summon/events', {
      method: 'POST',
      body: JSON.stringify(payload),
      silent: true,
    });
    return true;
  } catch {
    if (countAsDropped && payload.event_type !== 'dropped_report') {
      addPendingDroppedEvents(payload.surface, payload.count ?? 1);
    }
    return false;
  }
}

async function flushDroppedEvents(contextKey: string): Promise<void> {
  if (totalPendingDroppedEvents() <= 0) {
    return;
  }
  let changed = false;
  for (const surface of SUMMON_SURFACES) {
    const droppedCount = pendingDroppedEventsBySurface[surface];
    if (droppedCount <= 0) {
      continue;
    }
    pendingDroppedEventsBySurface[surface] = 0;
    changed = true;
    const flushed = await postExpertSummonEvent(
      {
        event_type: 'dropped_report',
        surface,
        context_key: contextKey,
        count: droppedCount,
      },
      false,
    );
    if (!flushed) {
      addPendingDroppedEvents(surface, droppedCount);
    }
  }
  if (changed) {
    persistDroppedBufferToStorage();
  }
}

function enqueueExpertSummonEvent(payload: ExpertSummonMetricEventPayload, contextKey: string): void {
  postQueue = postQueue
    .then(async () => {
      const posted = await postExpertSummonEvent(payload);
      if (posted) {
        await flushDroppedEvents(contextKey);
      }
    })
    .catch(() => {
      // Keep queue alive after unexpected runtime errors.
    });
}

function enqueueSimpleEvent(
  eventType: Exclude<ExpertSummonMetricEventType, 'dropped_report'>,
  surface: ExpertSummonMetricSurface,
  options?: {
    contextKey?: string;
    trigger?: ExpertSummonMetricTrigger;
    templateKind?: ExpertTemplateKind;
    fromSearch?: boolean;
    usedUseCase?: boolean;
    queryLength?: number;
    failureReason?: ExpertSummonFailureReason;
  },
): void {
  const normalizedContextKey = normalizeContextKey(options?.contextKey);
  enqueueExpertSummonEvent(
    {
      event_type: eventType,
      surface,
      context_key: normalizedContextKey,
      count: 1,
      trigger: options?.trigger,
      template_kind: options?.templateKind,
      from_search: options?.fromSearch,
      used_use_case: options?.usedUseCase,
      query_length: options?.queryLength === undefined ? undefined : clampQueryLength(options.queryLength),
      failure_reason: options?.failureReason,
    },
    normalizedContextKey,
  );
}

export function inferExpertSummonFailureReason(error: unknown): ExpertSummonFailureReason {
  if (error instanceof DOMException && error.name === 'AbortError') {
    return 'unknown_error';
  }
  if (error instanceof TypeError) {
    return 'network_error';
  }
  if (error instanceof Error) {
    const message = error.message.toLowerCase();
    if (message.includes('network') || message.includes('fetch')) {
      return 'network_error';
    }
    if (message.includes('5') || message.includes('server')) {
      return 'server_error';
    }
  }
  return 'unknown_error';
}

export function recordExpertSummonSurfaceViewed(
  surface: ExpertSummonMetricSurface,
  contextKey?: string,
): void {
  enqueueSimpleEvent('surface_viewed', surface, { contextKey });
}

export function recordExpertSummonSearchUsed(
  surface: ExpertSummonMetricSurface,
  queryLength: number,
  contextKey?: string,
): void {
  enqueueSimpleEvent('search_used', surface, { contextKey, queryLength });
}

export function recordExpertSummonAttempted(
  surface: ExpertSummonMetricSurface,
  trigger: ExpertSummonMetricTrigger,
  options?: {
    contextKey?: string;
    templateKind?: ExpertTemplateKind;
    fromSearch?: boolean;
    usedUseCase?: boolean;
  },
): void {
  enqueueSimpleEvent('summon_attempted', surface, {
    contextKey: options?.contextKey,
    trigger,
    templateKind: options?.templateKind,
    fromSearch: options?.fromSearch,
    usedUseCase: options?.usedUseCase,
  });
}

export function recordExpertSummonSucceeded(
  surface: ExpertSummonMetricSurface,
  trigger: ExpertSummonMetricTrigger,
  options?: {
    contextKey?: string;
    templateKind?: ExpertTemplateKind;
    fromSearch?: boolean;
    usedUseCase?: boolean;
  },
): void {
  enqueueSimpleEvent('summon_succeeded', surface, {
    contextKey: options?.contextKey,
    trigger,
    templateKind: options?.templateKind,
    fromSearch: options?.fromSearch,
    usedUseCase: options?.usedUseCase,
  });
}

export function recordExpertSummonFailed(
  surface: ExpertSummonMetricSurface,
  trigger: ExpertSummonMetricTrigger,
  failureReason: ExpertSummonFailureReason,
  options?: {
    contextKey?: string;
    templateKind?: ExpertTemplateKind;
    fromSearch?: boolean;
    usedUseCase?: boolean;
  },
): void {
  enqueueSimpleEvent('summon_failed', surface, {
    contextKey: options?.contextKey,
    trigger,
    templateKind: options?.templateKind,
    fromSearch: options?.fromSearch,
    usedUseCase: options?.usedUseCase,
    failureReason,
  });
}

export function recordExpertSummonRouteApplied(
  surface: ExpertSummonMetricSurface,
  trigger: ExpertSummonMetricTrigger,
  options?: {
    contextKey?: string;
    templateKind?: ExpertTemplateKind;
    fromSearch?: boolean;
    usedUseCase?: boolean;
  },
): void {
  enqueueSimpleEvent('route_applied', surface, {
    contextKey: options?.contextKey,
    trigger,
    templateKind: options?.templateKind,
    fromSearch: options?.fromSearch,
    usedUseCase: options?.usedUseCase,
  });
}

export function recordExpertSummonRouteApplyFailed(
  surface: ExpertSummonMetricSurface,
  trigger: ExpertSummonMetricTrigger,
  options?: {
    contextKey?: string;
    templateKind?: ExpertTemplateKind;
    fromSearch?: boolean;
    usedUseCase?: boolean;
  },
): void {
  enqueueSimpleEvent('route_apply_failed', surface, {
    contextKey: options?.contextKey,
    trigger,
    templateKind: options?.templateKind,
    fromSearch: options?.fromSearch,
    usedUseCase: options?.usedUseCase,
    failureReason: 'route_apply_failed',
  });
}

export function recordExpertSummonFirstMessageSent(
  surface: ExpertSummonMetricSurface,
  trigger: ExpertSummonMetricTrigger,
  options?: {
    contextKey?: string;
    templateKind?: ExpertTemplateKind;
    fromSearch?: boolean;
    usedUseCase?: boolean;
  },
): void {
  enqueueSimpleEvent('first_message_sent', surface, {
    contextKey: options?.contextKey,
    trigger,
    templateKind: options?.templateKind,
    fromSearch: options?.fromSearch,
    usedUseCase: options?.usedUseCase,
  });
}

export async function getExpertSummonSummary(days: number = 30): Promise<ExpertSummonSummary> {
  return apiRequest<ExpertSummonSummary>(`/statistics/expert-summon/summary?days=${days}`);
}

export async function __flushExpertSummonMetricsForTest(): Promise<void> {
  await postQueue;
}

export function __resetExpertSummonMetricsForTest(): void {
  pendingDroppedEventsBySurface = createEmptyDroppedBuffer();
  postQueue = Promise.resolve();
  if (typeof window !== 'undefined') {
    window.localStorage.removeItem(DROPPED_BUFFER_STORAGE_KEY);
  }
}
