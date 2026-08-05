'use client';

/**
 * [INPUT]
 * memoryLifecyclePhases (POS: lifecycle phase derivation helpers)
 * @/services/statistics::getSessionExecutionTrace (POS: session execution trace + memory_events)
 *
 * [OUTPUT]
 * useMessageMemoryLifecycle: Subscribe to memory_operation SSE for one chat + merge recall props;
 * markExtractRetryPending for manual extract retry optimistic UI.
 *
 * [POS]
 * Chat message-scoped memory lifecycle hook for MemoryInsightPanel timeline.
 */

import { useCallback, useEffect, useMemo, useState } from 'react';

import type { MemoryBriefData, MemoryBriefStatus } from '@/store/chat/types';
import { getSessionExecutionTrace } from '@/services/statistics';

import {
  applyMemoryOperationToPhases,
  hydratePhasesFromTraceEvents,
  initialMemoryLifecyclePhases,
  markExtractPhasePending,
  mergeRecallSeedIntoPhases,
  isMemoryEventForMessage,
  resolveMessageCreatedAtMs,
  memoryOperationMatchesChat,
  type MemoryLifecyclePhaseState,
  type MemoryLifecyclePhaseId,
  type MemoryOperationStreamPayload,
} from '@/components/features/message-box/memoryLifecyclePhases';

interface UseMessageMemoryLifecycleOptions {
  chatId: string | null | undefined;
  messageCreatedAtMs?: number;
  memoryBrief?: MemoryBriefData;
  memoryBriefStatus?: MemoryBriefStatus;
  citations?: string[];
  /** When false, write/extract phases stay idle (historical messages). */
  trackWriteExtract?: boolean;
}

interface UseMessageMemoryLifecycleResult {
  phases: Record<MemoryLifecyclePhaseId, MemoryLifecyclePhaseState>;
  markExtractRetryPending: () => void;
}

export function useMessageMemoryLifecycle({
  chatId,
  messageCreatedAtMs,
  memoryBrief,
  memoryBriefStatus,
  citations,
  trackWriteExtract = false,
}: UseMessageMemoryLifecycleOptions): UseMessageMemoryLifecycleResult {
  const scopedMessageCreatedAtMs = resolveMessageCreatedAtMs(messageCreatedAtMs);

  const recallSeed = useMemo(
    () => initialMemoryLifecyclePhases(memoryBrief, memoryBriefStatus, citations),
    [memoryBrief, memoryBriefStatus, citations],
  );

  const [phases, setPhases] = useState(recallSeed);

  useEffect(() => {
    setPhases((current) => mergeRecallSeedIntoPhases(current, recallSeed));
  }, [recallSeed]);

  useEffect(() => {
    if (!trackWriteExtract || !chatId) return;

    let cancelled = false;

    void getSessionExecutionTrace(chatId)
      .then((trace) => {
        if (cancelled) return;
        const events = trace.memory_events ?? [];
        if (events.length === 0) return;
        setPhases((current) =>
          hydratePhasesFromTraceEvents(current, events, scopedMessageCreatedAtMs),
        );
      })
      .catch(() => {
        // Hydrate is best-effort; live SSE remains primary.
      });

    return () => {
      cancelled = true;
    };
  }, [chatId, scopedMessageCreatedAtMs, trackWriteExtract]);

  useEffect(() => {
    if (!trackWriteExtract || !chatId) return;

    const handler = (event: Event) => {
      const detail = (event as CustomEvent<MemoryOperationStreamPayload>).detail;
      if (!detail || !memoryOperationMatchesChatScoped(detail)) return;
      setPhases((current) => applyMemoryOperationToPhases(current, detail));
    };

    function memoryOperationMatchesChatScoped(detail: MemoryOperationStreamPayload): boolean {
      if (!chatId) return false;
      if (scopedMessageCreatedAtMs == null) {
        return memoryOperationMatchesChat(detail, chatId);
      }
      return isMemoryEventForMessage(detail, chatId, scopedMessageCreatedAtMs);
    }

    window.addEventListener('memory_operation', handler);
    return () => window.removeEventListener('memory_operation', handler);
  }, [chatId, scopedMessageCreatedAtMs, trackWriteExtract]);

  const markExtractRetryPending = useCallback(() => {
    setPhases((current) => markExtractPhasePending(current));
  }, []);

  return { phases, markExtractRetryPending };
}
