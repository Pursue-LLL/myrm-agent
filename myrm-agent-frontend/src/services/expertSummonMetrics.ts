/**
 * [INPUT]
 * - @/lib/api::apiRequest (POS: 前端 API 接入层。统一请求基址、超时、错误归一化。)
 *
 * [OUTPUT]
 * - recordExpertSummon*: 专家召唤漏斗事件写入。
 * - getExpertSummonSummary: 专家召唤漏斗聚合查询。
 *
 * [POS]
 * 专家召唤漏斗可观测客户端。负责 ExpertSummonPopover/FeaturedExpertChips/FlowPad 的统一埋点口径、
 * 离线丢样聚合回补，以及主路径成功率/失败率/首条发送转化率观测。
 */
import { ApiError, apiRequest } from '@/lib/api';
import { BACKEND_UNREACHABLE_CODE } from '@/lib/local-backend-dev';
import type { ExpertTemplateKind } from '@/services/templateDiscovery';

export type ExpertSummonMetricSurface =
  'template_market' | 'flow_pad_inline' | 'empty_chat_featured' | 'message_input_plus' | 'mobile_hub_chip';
export type ExpertSummonMetricTrigger =
  'template_card' | 'use_case_chip' | 'route_menu' | 'featured_chip' | 'plus_popover_card' | 'mobile_chip';
export type ExpertSummonMetricEventType =
  | 'surface_viewed'
  | 'search_used'
  | 'summon_attempted'
  | 'summon_succeeded'
  | 'summon_failed'
  | 'route_applied'
  | 'route_apply_failed'
  | 'first_message_sent'
  | 'council_phase_completed'
  | 'council_consensus_reached'
  | 'expert_rebuttal_effective'
  | 'dropped_report';
export type ExpertSummonFailureReason = 'network_error' | 'route_apply_failed' | 'server_error' | 'unknown_error';

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

/** The most events one request may carry; the server rejects a larger `count`. */
const MAX_COUNT_PER_REQUEST = 200;
const MAX_QUERY_LENGTH = 200;
/** The longest `context_key` the server accepts; a longer one makes it reject the whole event. */
const MAX_CONTEXT_KEY_LENGTH = 128;
const MAX_PENDING_DROPPED_EVENTS = 1_000;
const DEFAULT_CONTEXT_KEY = 'global';
const DROPPED_BUFFER_STORAGE_KEY = 'expertSummonDroppedBufferV1';
const SUMMON_SURFACES: ExpertSummonMetricSurface[] = [
  'template_market',
  'flow_pad_inline',
  'empty_chat_featured',
  'message_input_plus',
  'mobile_hub_chip',
];

let pendingDroppedEventsBySurface = loadDroppedBufferFromStorage();
let postQueue: Promise<void> = Promise.resolve();

/** A whole number in `0..max`; anything that is not a finite number counts as 0. */
function clampWhole(value: number | undefined, max: number): number {
  if (value === undefined || !Number.isFinite(value)) {
    return 0;
  }
  return Math.max(0, Math.min(max, Math.floor(value)));
}

function normalizeContextKey(contextKey?: string): string {
  // The server counts characters, so cut by characters: an emoji at the limit must not be split in half.
  const normalized = Array.from(contextKey?.trim() ?? '')
    .slice(0, MAX_CONTEXT_KEY_LENGTH)
    .join('');
  return normalized || DEFAULT_CONTEXT_KEY;
}

function totalPendingDroppedEvents(): number {
  return SUMMON_SURFACES.reduce((sum, surface) => sum + pendingDroppedEventsBySurface[surface], 0);
}

function createEmptyDroppedBuffer(): Record<ExpertSummonMetricSurface, number> {
  return {
    template_market: 0,
    flow_pad_inline: 0,
    empty_chat_featured: 0,
    message_input_plus: 0,
    mobile_hub_chip: 0,
  };
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
    const buffer = createEmptyDroppedBuffer();
    for (const surface of SUMMON_SURFACES) {
      buffer[surface] = clampWhole(parsed[surface], MAX_PENDING_DROPPED_EVENTS);
    }
    return buffer;
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

function addPendingDroppedEvent(surface: ExpertSummonMetricSurface): void {
  if (totalPendingDroppedEvents() >= MAX_PENDING_DROPPED_EVENTS) {
    return;
  }
  pendingDroppedEventsBySurface[surface] += 1;
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
    if (countAsDropped) {
      addPendingDroppedEvent(payload.surface);
    }
    return false;
  }
}

/**
 * Reports the events that could not be sent earlier. A backlog goes out in requests of at most
 * `MAX_COUNT_PER_REQUEST`, and a part leaves the buffer only once the server has taken it, so a refused
 * part is retried with the next event that gets through.
 */
async function flushDroppedEvents(contextKey: string): Promise<void> {
  let changed = false;
  for (const surface of SUMMON_SURFACES) {
    while (pendingDroppedEventsBySurface[surface] > 0) {
      const count = Math.min(pendingDroppedEventsBySurface[surface], MAX_COUNT_PER_REQUEST);
      const reported = await postExpertSummonEvent(
        { event_type: 'dropped_report', surface, context_key: contextKey, count },
        false,
      );
      if (!reported) {
        break;
      }
      pendingDroppedEventsBySurface[surface] -= count;
      changed = true;
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

interface SummonEventOptions {
  contextKey?: string;
  templateKind?: ExpertTemplateKind;
  fromSearch?: boolean;
  usedUseCase?: boolean;
}

interface CouncilEventOptions {
  contextKey?: string;
  templateKind?: ExpertTemplateKind;
}

interface SimpleEventOptions extends SummonEventOptions {
  trigger?: ExpertSummonMetricTrigger;
  queryLength?: number;
  failureReason?: ExpertSummonFailureReason;
}

function enqueueSimpleEvent(
  eventType: Exclude<ExpertSummonMetricEventType, 'dropped_report'>,
  surface: ExpertSummonMetricSurface,
  options?: SimpleEventOptions,
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
      query_length: options?.queryLength === undefined ? undefined : clampWhole(options.queryLength, MAX_QUERY_LENGTH),
      failure_reason: options?.failureReason,
    },
    normalizedContextKey,
  );
}

/** `ApiError.businessCode` values for a request that never got an answer from the server. */
const UNANSWERED_REQUEST_CODES: ReadonlySet<string> = new Set([
  'NETWORK_ERROR',
  'TIMEOUT_ERROR',
  BACKEND_UNREACHABLE_CODE,
]);

export function inferExpertSummonFailureReason(error: unknown): ExpertSummonFailureReason {
  if (error instanceof DOMException && error.name === 'AbortError') {
    return 'unknown_error';
  }
  if (error instanceof ApiError) {
    if (error.businessCode && UNANSWERED_REQUEST_CODES.has(error.businessCode)) {
      return 'network_error';
    }
    // For answers from the server `code` is the HTTP status; the message is the server's own words.
    return error.code >= 500 ? 'server_error' : 'unknown_error';
  }
  if (error instanceof TypeError) {
    return 'network_error';
  }
  if (error instanceof Error) {
    const message = error.message.toLowerCase();
    if (message.includes('network') || message.includes('fetch')) {
      return 'network_error';
    }
    if (/\b5\d{2}\b/.test(message) || message.includes('server')) {
      return 'server_error';
    }
  }
  return 'unknown_error';
}

export function recordExpertSummonSurfaceViewed(surface: ExpertSummonMetricSurface, contextKey?: string): void {
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
  options?: SummonEventOptions,
): void {
  enqueueSimpleEvent('summon_attempted', surface, { ...options, trigger });
}

export function recordExpertSummonSucceeded(
  surface: ExpertSummonMetricSurface,
  trigger: ExpertSummonMetricTrigger,
  options?: SummonEventOptions,
): void {
  enqueueSimpleEvent('summon_succeeded', surface, { ...options, trigger });
}

export function recordExpertSummonFailed(
  surface: ExpertSummonMetricSurface,
  trigger: ExpertSummonMetricTrigger,
  failureReason: ExpertSummonFailureReason,
  options?: SummonEventOptions,
): void {
  enqueueSimpleEvent('summon_failed', surface, { ...options, trigger, failureReason });
}

export function recordExpertSummonRouteApplied(
  surface: ExpertSummonMetricSurface,
  trigger: ExpertSummonMetricTrigger,
  options?: SummonEventOptions,
): void {
  enqueueSimpleEvent('route_applied', surface, { ...options, trigger });
}

export function recordExpertSummonRouteApplyFailed(
  surface: ExpertSummonMetricSurface,
  trigger: ExpertSummonMetricTrigger,
  options?: SummonEventOptions,
): void {
  enqueueSimpleEvent('route_apply_failed', surface, { ...options, trigger, failureReason: 'route_apply_failed' });
}

export function recordExpertSummonFirstMessageSent(
  surface: ExpertSummonMetricSurface,
  trigger: ExpertSummonMetricTrigger,
  options?: SummonEventOptions,
): void {
  enqueueSimpleEvent('first_message_sent', surface, { ...options, trigger });
}

export function recordExpertCouncilPhaseCompleted(
  surface: ExpertSummonMetricSurface,
  trigger: ExpertSummonMetricTrigger,
  options?: CouncilEventOptions,
): void {
  enqueueSimpleEvent('council_phase_completed', surface, { ...options, trigger });
}

export function recordExpertCouncilConsensusReached(
  surface: ExpertSummonMetricSurface,
  trigger: ExpertSummonMetricTrigger,
  options?: CouncilEventOptions,
): void {
  enqueueSimpleEvent('council_consensus_reached', surface, { ...options, trigger });
}

export function recordExpertRebuttalEffective(
  surface: ExpertSummonMetricSurface,
  trigger: ExpertSummonMetricTrigger,
  options?: CouncilEventOptions,
): void {
  enqueueSimpleEvent('expert_rebuttal_effective', surface, { ...options, trigger });
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
