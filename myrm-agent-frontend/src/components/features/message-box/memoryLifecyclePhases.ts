/**
 * [OUTPUT] memoryLifecyclePhases: Derive write/extract/recall phase states; manual retry optimistic merge.
 * [POS] Pure helpers — maps ledger SSE payloads + message recall props to lifecycle UI states.
 */

import type { MemoryBriefData, MemoryBriefStatus } from '@/store/chat/types';

export type MemoryLifecyclePhaseId = 'write' | 'extract' | 'recall';

export type MemoryLifecyclePhaseStatus = 'pending' | 'success' | 'skipped' | 'error' | 'idle';

export interface MemoryLifecyclePhaseState {
  id: MemoryLifecyclePhaseId;
  status: MemoryLifecyclePhaseStatus;
  detail?: string;
  durationMs?: number;
  /** Cards persisted on extract success (from ledger/SSE metadata.stored_count). */
  storedCount?: number;
  /** Verbatim chunks when compressed cards are zero (metadata.verbatim_count). */
  verbatimCount?: number;
}

export interface MemoryOperationStreamPayload {
  kind?: string;
  status?: string;
  description?: string;
  target_id?: string | null;
  metadata?: Record<string, unknown>;
  chat_id?: string;
  operation?: string;
  occurred_at?: string;
}

function eventChatId(payload: MemoryOperationStreamPayload): string | null {
  const meta = payload.metadata;
  if (meta && typeof meta.chat_id === 'string' && meta.chat_id.trim()) {
    return meta.chat_id.trim();
  }
  if (typeof payload.target_id === 'string' && payload.target_id.trim()) {
    return payload.target_id.trim();
  }
  if (typeof payload.chat_id === 'string' && payload.chat_id.trim()) {
    return payload.chat_id.trim();
  }
  return null;
}

export function memoryOperationMatchesChat(
  payload: MemoryOperationStreamPayload,
  chatId: string | null | undefined,
): boolean {
  if (!chatId) {
    return false;
  }
  const resolved = eventChatId(payload);
  return resolved === chatId;
}

export interface TraceMemoryEventLike {
  kind?: string;
  phase?: string;
  status: string;
  summary: string;
  target_id?: string | null;
  metadata?: Record<string, unknown>;
  timestamp?: number;
}

const MESSAGE_EVENT_SKEW_MS = 5000;

/** Normalize API/store message timestamps for P1 lifecycle scoping (ISO string or Date). */
export function resolveMessageCreatedAtMs(createdAt: Date | string | number | null | undefined): number | undefined {
  if (createdAt instanceof Date) {
    const ms = createdAt.getTime();
    return Number.isFinite(ms) ? ms : undefined;
  }
  if (typeof createdAt === 'string' || typeof createdAt === 'number') {
    const ms = typeof createdAt === 'number' ? createdAt : Date.parse(createdAt);
    return Number.isFinite(ms) ? ms : undefined;
  }
  return undefined;
}

export function memoryEventTimestampMs(payload: MemoryOperationStreamPayload): number | null {
  if (typeof payload.occurred_at === 'string') {
    const ms = Date.parse(payload.occurred_at);
    if (Number.isFinite(ms)) {
      return ms;
    }
  }
  const metaOccurred = payload.metadata?.occurred_at;
  if (typeof metaOccurred === 'string') {
    const ms = Date.parse(metaOccurred);
    if (Number.isFinite(ms)) {
      return ms;
    }
  }
  return null;
}

export function traceMemoryEventTimestampMs(event: TraceMemoryEventLike): number | null {
  if (typeof event.timestamp === 'number' && Number.isFinite(event.timestamp)) {
    return event.timestamp * 1000;
  }
  return null;
}

export function isMemoryEventForMessage(
  payload: MemoryOperationStreamPayload,
  chatId: string,
  messageCreatedAtMs: number,
): boolean {
  if (!memoryOperationMatchesChat(payload, chatId)) {
    return false;
  }
  const eventMs = memoryEventTimestampMs(payload);
  if (eventMs == null) {
    return false;
  }
  return eventMs >= messageCreatedAtMs - MESSAGE_EVENT_SKEW_MS;
}

export function isTraceMemoryEventForMessage(event: TraceMemoryEventLike, messageCreatedAtMs: number): boolean {
  const eventMs = traceMemoryEventTimestampMs(event);
  if (eventMs == null) {
    return false;
  }
  return eventMs >= messageCreatedAtMs - MESSAGE_EVENT_SKEW_MS;
}

function mapLedgerStatus(raw: string | undefined): MemoryLifecyclePhaseStatus {
  switch (raw) {
    case 'pending':
      return 'pending';
    case 'success':
      return 'success';
    case 'skipped':
      return 'skipped';
    case 'error':
    case 'warning':
      return 'error';
    default:
      return 'idle';
  }
}

/** Optimistic extract pending after manual retry API accepts (SSE remains authoritative). */
export function markExtractPhasePending(
  phases: Record<MemoryLifecyclePhaseId, MemoryLifecyclePhaseState>,
): Record<MemoryLifecyclePhaseId, MemoryLifecyclePhaseState> {
  return {
    ...phases,
    extract: { id: 'extract', status: 'pending' },
  };
}

/** Preserve write/extract SSE or optimistic state when recall props refresh. */
export function mergeRecallSeedIntoPhases(
  current: Record<MemoryLifecyclePhaseId, MemoryLifecyclePhaseState>,
  recallSeed: Record<MemoryLifecyclePhaseId, MemoryLifecyclePhaseState>,
): Record<MemoryLifecyclePhaseId, MemoryLifecyclePhaseState> {
  return {
    ...recallSeed,
    write: current.write.status !== 'idle' ? current.write : recallSeed.write,
    extract: current.extract.status !== 'idle' ? current.extract : recallSeed.extract,
  };
}

export function applyMemoryOperationToPhases(
  phases: Record<MemoryLifecyclePhaseId, MemoryLifecyclePhaseState>,
  payload: MemoryOperationStreamPayload,
): Record<MemoryLifecyclePhaseId, MemoryLifecyclePhaseState> {
  const kind = String(payload.kind ?? '');
  const next = { ...phases };
  const status = mapLedgerStatus(String(payload.status ?? ''));
  const detail = typeof payload.description === 'string' ? payload.description : undefined;
  const rawDuration = payload.metadata?.duration_ms;
  const durationMs = typeof rawDuration === 'number' ? rawDuration : undefined;
  const rawStored = payload.metadata?.stored_count ?? payload.metadata?.compressed_count;
  const storedCount = typeof rawStored === 'number' ? rawStored : undefined;
  const rawVerbatim = payload.metadata?.verbatim_count;
  const verbatimCount = typeof rawVerbatim === 'number' ? rawVerbatim : undefined;

  if (kind === 'write') {
    next.write = { id: 'write', status, detail };
  } else if (kind === 'extract') {
    next.extract = {
      id: 'extract',
      status,
      detail,
      durationMs: durationMs ?? phases.extract.durationMs,
      storedCount: storedCount ?? phases.extract.storedCount,
      verbatimCount: verbatimCount ?? phases.extract.verbatimCount,
    };
  } else if (kind === 'inject' || kind === 'recall') {
    next.recall = { id: 'recall', status, detail };
  }

  return next;
}

export function deriveRecallPhaseFromMessage(
  memoryBrief?: MemoryBriefData,
  memoryBriefStatus?: MemoryBriefStatus,
  citations?: string[],
): MemoryLifecyclePhaseState {
  if (memoryBrief || (citations && citations.length > 0)) {
    return { id: 'recall', status: 'success' };
  }
  if (memoryBriefStatus?.state === 'skipped') {
    return { id: 'recall', status: 'skipped' };
  }
  return { id: 'recall', status: 'idle' };
}

export function initialMemoryLifecyclePhases(
  memoryBrief?: MemoryBriefData,
  memoryBriefStatus?: MemoryBriefStatus,
  citations?: string[],
): Record<MemoryLifecyclePhaseId, MemoryLifecyclePhaseState> {
  return {
    write: { id: 'write', status: 'idle' },
    extract: { id: 'extract', status: 'idle' },
    recall: deriveRecallPhaseFromMessage(memoryBrief, memoryBriefStatus, citations),
  };
}

export function hasVisibleLifecycle(
  phases: Record<MemoryLifecyclePhaseId, MemoryLifecyclePhaseState>,
  options?: { writeExtractOnly?: boolean },
): boolean {
  if (options?.writeExtractOnly) {
    return phases.write.status !== 'idle' || phases.extract.status !== 'idle';
  }
  return (Object.values(phases) as MemoryLifecyclePhaseState[]).some((phase) => phase.status !== 'idle');
}

function ledgerKindFromTraceEvent(event: TraceMemoryEventLike): string {
  if (event.kind && event.kind.trim()) {
    return event.kind.trim();
  }
  if (event.phase === 'write') {
    return 'write';
  }
  if (event.phase === 'observe') {
    return 'extract';
  }
  if (event.phase === 'recall' || event.phase === 'inject') {
    return 'recall';
  }
  return '';
}

export function traceMemoryEventToPayload(event: TraceMemoryEventLike): MemoryOperationStreamPayload {
  return {
    kind: ledgerKindFromTraceEvent(event),
    status: event.status,
    description: event.summary,
    target_id: event.target_id ?? undefined,
    metadata: event.metadata,
  };
}

export function hydratePhasesFromTraceEvents(
  base: Record<MemoryLifecyclePhaseId, MemoryLifecyclePhaseState>,
  events: TraceMemoryEventLike[],
  messageCreatedAtMs?: number,
): Record<MemoryLifecyclePhaseId, MemoryLifecyclePhaseState> {
  const scopedAtMs = messageCreatedAtMs != null && Number.isFinite(messageCreatedAtMs) ? messageCreatedAtMs : undefined;
  const scopedEvents =
    scopedAtMs == null ? events : events.filter((event) => isTraceMemoryEventForMessage(event, scopedAtMs));
  return scopedEvents.reduce(
    (current, event) => applyMemoryOperationToPhases(current, traceMemoryEventToPayload(event)),
    base,
  );
}
