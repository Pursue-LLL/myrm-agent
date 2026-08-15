/**
 * [INPUT]
 * @/lib/api::apiRequest (POS: frontend API request helper)
 * @/store/chat/types::WikiSourceLevel (POS: Wiki 源层级类型)
 *
 * [OUTPUT]
 * 证据曝光/展开/核验停留/query attempt+success/负向结果事件记录与聚合摘要查询 API。
 *
 * [POS]
 * Wiki 证据指标客户端。`/statistics/wiki-evidence/*` REST 契约（按 context_key 隔离复问口径）。
 */

import { apiRequest } from '@/lib/api';
import type { WikiSourceLevel } from '@/store/chat/types';

export type WikiEvidenceSnapshotStatus = 'verified' | 'stale' | 'missing';
export type WikiEvidenceSurface = 'chat' | 'settings';
type WikiEvidenceEventType =
  | 'evidence_surface'
  | 'snippet_open'
  | 'snippet_close'
  | 'query_attempted'
  | 'query_submitted'
  | 'dropped_report'
  | 'quality_outcome_negative';

interface WikiEvidenceEventPayload {
  event_type: WikiEvidenceEventType;
  surface: WikiEvidenceSurface;
  context_key?: string;
  level?: WikiSourceLevel;
  snapshot_status?: WikiEvidenceSnapshotStatus;
  count?: number;
  dwell_ms?: number;
  after_evidence?: boolean;
  turn_distance?: number;
}

export interface WikiEvidenceSummary {
  days: number;
  retention_days: number;
  total_events: number;
  evidence_surface_count: number;
  snippet_open_count: number;
  dropped_event_count: number;
  snippet_expansion_rate: number;
  deep_verification_count: number;
  deep_verification_rate: number;
  quick_bounce_count: number;
  quick_bounce_rate: number;
  quality_outcome_negative_count: number;
  quality_outcome_negative_rate: number;
  query_attempt_count: number;
  query_success_count: number;
  query_success_rate: number;
  query_count: number;
  requery_count: number;
  requery_rate: number;
  verification_dwell_avg_ms: number;
  verification_dwell_sample_count: number;
  snippet_open_by_surface: Record<WikiEvidenceSurface, number>;
  snippet_open_by_level: Record<WikiSourceLevel, number>;
  quality_outcome_negative_by_surface: Record<WikiEvidenceSurface, number>;
}

const MAX_EVENT_COUNT = 200;
const MAX_DWELL_MS = 1_800_000; // 30m
const MAX_TURN_DISTANCE = 500;
const REQUERY_WINDOW_MS = 10 * 60 * 1000;
const MAX_PENDING_DROPPED_EVENTS = 1_000;
const DEFAULT_CONTEXT_KEY = 'global';
const EVIDENCE_SURFACES: WikiEvidenceSurface[] = ['chat', 'settings'];
const DROPPED_BUFFER_STORAGE_KEY = 'wikiEvidenceDroppedBufferV1';

const lastEvidenceInteractionAtMsByContext = new Map<string, number>();
const pendingDroppedEventsBySurface = loadDroppedBufferFromStorage();
let postQueue: Promise<void> = Promise.resolve();

function normalizeContextKey(contextKey?: string): string {
  const normalized = contextKey?.trim();
  return normalized && normalized.length > 0 ? normalized : DEFAULT_CONTEXT_KEY;
}

async function postWikiEvidenceEvent(payload: WikiEvidenceEventPayload, countAsDropped: boolean = true): Promise<boolean> {
  try {
    await apiRequest('/statistics/wiki-evidence/events', {
      method: 'POST',
      body: JSON.stringify(payload),
      silent: true,
    });
    return true;
  } catch {
    if (countAsDropped && payload.event_type !== 'dropped_report') {
      const increment = clampCount(payload.count ?? 1);
      addPendingDroppedEvents(payload.surface, increment);
    }
    return false;
  }
}

async function flushDroppedEvents(contextKey: string): Promise<void> {
  if (totalPendingDroppedEvents() <= 0) {
    return;
  }
  let changed = false;
  for (const surface of EVIDENCE_SURFACES) {
    const droppedCount = pendingDroppedEventsBySurface[surface];
    if (droppedCount <= 0) {
      continue;
    }
    pendingDroppedEventsBySurface[surface] = 0;
    changed = true;
    const flushed = await postWikiEvidenceEvent(
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

function enqueueWikiEvidenceEvent(payload: WikiEvidenceEventPayload, contextKey: string): void {
  postQueue = postQueue
    .then(async () => {
      const posted = await postWikiEvidenceEvent(payload);
      if (posted) {
        await flushDroppedEvents(contextKey);
      }
    })
    .catch(() => {
      // Keep queue alive even if an unexpected runtime error happens.
    });
}

function markEvidenceInteraction(contextKey: string): void {
  lastEvidenceInteractionAtMsByContext.set(contextKey, Date.now());
}

function consumeRequeryWindow(contextKey: string): boolean {
  const nowMs = Date.now();
  const lastInteractionAtMs = lastEvidenceInteractionAtMsByContext.get(contextKey);
  const matched =
    lastInteractionAtMs !== undefined && nowMs - lastInteractionAtMs >= 0 && nowMs - lastInteractionAtMs <= REQUERY_WINDOW_MS;
  if (matched) {
    lastEvidenceInteractionAtMsByContext.delete(contextKey);
  }
  return matched;
}

function clampCount(count: number): number {
  if (!Number.isFinite(count)) {return 1;}
  return Math.max(1, Math.min(MAX_EVENT_COUNT, Math.floor(count)));
}

function clampDwellMs(dwellMs: number): number {
  if (!Number.isFinite(dwellMs)) {return 0;}
  return Math.max(0, Math.min(MAX_DWELL_MS, Math.floor(dwellMs)));
}

function clampTurnDistance(turnDistance: number | undefined): number | undefined {
  if (turnDistance === undefined || !Number.isFinite(turnDistance)) {
    return undefined;
  }
  return Math.max(0, Math.min(MAX_TURN_DISTANCE, Math.floor(turnDistance)));
}

function totalPendingDroppedEvents(): number {
  return pendingDroppedEventsBySurface.chat + pendingDroppedEventsBySurface.settings;
}

function addPendingDroppedEvents(surface: WikiEvidenceSurface, increment: number): void {
  const totalPending = totalPendingDroppedEvents();
  const remainingCapacity = Math.max(0, MAX_PENDING_DROPPED_EVENTS - totalPending);
  if (remainingCapacity <= 0) {
    return;
  }
  const acceptedIncrement = Math.min(remainingCapacity, increment);
  pendingDroppedEventsBySurface[surface] += acceptedIncrement;
  persistDroppedBufferToStorage();
}

function createEmptyDroppedBuffer(): Record<WikiEvidenceSurface, number> {
  return {
    chat: 0,
    settings: 0,
  };
}

function loadDroppedBufferFromStorage(): Record<WikiEvidenceSurface, number> {
  if (typeof window === 'undefined') {
    return createEmptyDroppedBuffer();
  }
  try {
    const raw = window.localStorage.getItem(DROPPED_BUFFER_STORAGE_KEY);
    if (!raw) {
      return createEmptyDroppedBuffer();
    }
    const parsed = JSON.parse(raw) as Partial<Record<WikiEvidenceSurface, number>>;
    return {
      chat: clampPendingCount(parsed.chat),
      settings: clampPendingCount(parsed.settings),
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
    // Storage failure should never block telemetry.
  }
}

function clampPendingCount(count: number | undefined): number {
  if (count === undefined || !Number.isFinite(count)) {
    return 0;
  }
  return Math.max(0, Math.min(MAX_PENDING_DROPPED_EVENTS, Math.floor(count)));
}

export function recordEvidenceSurface(surface: WikiEvidenceSurface, count: number = 1, contextKey?: string): void {
  if (count <= 0) {
    return;
  }
  const normalizedContextKey = normalizeContextKey(contextKey);
  enqueueWikiEvidenceEvent(
    {
      event_type: 'evidence_surface',
      surface,
      context_key: normalizedContextKey,
      count: clampCount(count),
    },
    normalizedContextKey,
  );
}

export function recordSnippetOpen(
  surface: WikiEvidenceSurface,
  level?: WikiSourceLevel,
  contextKey?: string,
  snapshotStatus?: WikiEvidenceSnapshotStatus,
): void {
  const normalizedContextKey = normalizeContextKey(contextKey);
  markEvidenceInteraction(normalizedContextKey);
  enqueueWikiEvidenceEvent(
    {
      event_type: 'snippet_open',
      surface,
      context_key: normalizedContextKey,
      level,
      snapshot_status: snapshotStatus,
    },
    normalizedContextKey,
  );
}

export function recordSnippetClose(surface: WikiEvidenceSurface, dwellMs: number, contextKey?: string): void {
  const normalizedContextKey = normalizeContextKey(contextKey);
  markEvidenceInteraction(normalizedContextKey);
  enqueueWikiEvidenceEvent(
    {
      event_type: 'snippet_close',
      surface,
      context_key: normalizedContextKey,
      dwell_ms: clampDwellMs(dwellMs),
    },
    normalizedContextKey,
  );
}

export function recordWikiQueryAttempt(
  surface: WikiEvidenceSurface = 'settings',
  contextKey?: string,
  turnDistance?: number,
): void {
  const normalizedContextKey = normalizeContextKey(contextKey);
  enqueueWikiEvidenceEvent(
    {
      event_type: 'query_attempted',
      surface,
      context_key: normalizedContextKey,
      turn_distance: clampTurnDistance(turnDistance),
    },
    normalizedContextKey,
  );
}

export function recordWikiQuerySubmitted(
  surface: WikiEvidenceSurface = 'settings',
  contextKey?: string,
  turnDistance?: number,
): void {
  const normalizedContextKey = normalizeContextKey(contextKey);
  const afterEvidence = consumeRequeryWindow(normalizedContextKey);
  enqueueWikiEvidenceEvent(
    {
      event_type: 'query_submitted',
      surface,
      context_key: normalizedContextKey,
      after_evidence: afterEvidence,
      turn_distance: clampTurnDistance(turnDistance),
    },
    normalizedContextKey,
  );
}

export function recordQualityOutcomeNegative(surface: WikiEvidenceSurface = 'chat', count: number = 1, contextKey?: string): void {
  if (count <= 0) {
    return;
  }
  const normalizedContextKey = normalizeContextKey(contextKey);
  enqueueWikiEvidenceEvent(
    {
      event_type: 'quality_outcome_negative',
      surface,
      context_key: normalizedContextKey,
      count: clampCount(count),
    },
    normalizedContextKey,
  );
}

export async function getWikiEvidenceSummary(days: number = 30): Promise<WikiEvidenceSummary> {
  return apiRequest<WikiEvidenceSummary>(`/statistics/wiki-evidence/summary?days=${days}`);
}

export function __resetWikiEvidenceMetricsForTest(): void {
  lastEvidenceInteractionAtMsByContext.clear();
  pendingDroppedEventsBySurface.chat = 0;
  pendingDroppedEventsBySurface.settings = 0;
  persistDroppedBufferToStorage();
  postQueue = Promise.resolve();
}

export async function __flushWikiEvidenceMetricsForTest(): Promise<void> {
  await postQueue;
}
