import { describe, expect, it } from 'vitest';

import {
  applyMemoryOperationToPhases,
  deriveRecallPhaseFromMessage,
  hydratePhasesFromTraceEvents,
  initialMemoryLifecyclePhases,
  isMemoryEventForMessage,
  isTraceMemoryEventForMessage,
  markExtractPhasePending,
  mergeRecallSeedIntoPhases,
  memoryOperationMatchesChat,
  resolveMessageCreatedAtMs,
  traceMemoryEventToPayload,
} from '@/components/features/message-box/memoryLifecyclePhases';

describe('memoryLifecyclePhases', () => {
  it('matches chat via metadata.chat_id', () => {
    expect(
      memoryOperationMatchesChat(
        { kind: 'extract', metadata: { chat_id: 'chat-1' } },
        'chat-1',
      ),
    ).toBe(true);
    expect(
      memoryOperationMatchesChat(
        { kind: 'extract', metadata: { chat_id: 'chat-2' } },
        'chat-1',
      ),
    ).toBe(false);
  });

  it('marks extract pending for manual retry optimistic UI', () => {
    const errorPhases = {
      ...initialMemoryLifecyclePhases(),
      write: { id: 'write' as const, status: 'success' as const },
      extract: { id: 'extract' as const, status: 'error' as const, detail: 'failed' },
    };
    const pending = markExtractPhasePending(errorPhases);
    expect(pending.extract.status).toBe('pending');
    expect(pending.write.status).toBe('success');
  });

  it('preserves extract phase when recall seed refreshes', () => {
    const pendingPhases = markExtractPhasePending(initialMemoryLifecyclePhases());
    const refreshedRecall = {
      ...initialMemoryLifecyclePhases(),
      recall: { id: 'recall' as const, status: 'success' as const },
    };
    const merged = mergeRecallSeedIntoPhases(pendingPhases, refreshedRecall);
    expect(merged.extract.status).toBe('pending');
    expect(merged.recall.status).toBe('success');
  });

  it('applies extract pending then success', () => {
    const base = initialMemoryLifecyclePhases();
    const pending = applyMemoryOperationToPhases(base, {
      kind: 'extract',
      status: 'pending',
      description: 'Memory extraction started',
      metadata: { chat_id: 'c1' },
    });
    expect(pending.extract.status).toBe('pending');

    const done = applyMemoryOperationToPhases(pending, {
      kind: 'extract',
      status: 'success',
      description: 'Extracted 2 memory cards',
      metadata: { chat_id: 'c1', stored_count: 2, duration_ms: 842 },
    });
    expect(done.extract.status).toBe('success');
    expect(done.extract.storedCount).toBe(2);
    expect(done.extract.durationMs).toBe(842);
  });

  it('maps verbatim-only extract success to storedCount zero', () => {
    const done = applyMemoryOperationToPhases(initialMemoryLifecyclePhases(), {
      kind: 'extract',
      status: 'success',
      description: 'Verbatim only',
      metadata: { compressed_count: 0, verbatim_count: 1 },
    });
    expect(done.extract.storedCount).toBe(0);
    expect(done.extract.verbatimCount).toBe(1);
  });

  it('derives recall success from memory brief', () => {
    expect(
      deriveRecallPhaseFromMessage(
        {
          snapshot_id: 'snap-1',
          generated_at_ms: 0,
          namespaces: ['global'],
          is_cold_start: false,
          stable: { working_state: true, profile_keys: [], instruction_count: 0, rule_count: 0 },
          learned: { preference_count: 0, rule_count: 0, correction_count: 0, preference_ids: [], rule_ids: [] },
        },
      ).status,
    ).toBe('success');
  });

  it('hydrates extract duration from trace memory events', () => {
    const base = initialMemoryLifecyclePhases();
    const hydrated = hydratePhasesFromTraceEvents(base, [
      {
        kind: 'extract',
        phase: 'observe',
        status: 'success',
        summary: 'Extracted 2 memory cards',
        metadata: { duration_ms: 842 },
      },
    ]);
    expect(hydrated.extract.status).toBe('success');
    expect(hydrated.extract.durationMs).toBe(842);
  });

  it('maps trace observe phase to extract kind', () => {
    const payload = traceMemoryEventToPayload({
      phase: 'observe',
      status: 'pending',
      summary: 'Memory extraction started',
    });
    expect(payload.kind).toBe('extract');
  });

  it('filters SSE events older than message createdAt', () => {
    const messageCreatedAtMs = 1_700_000_000_000;
    const stalePayload = {
      kind: 'extract',
      status: 'success',
      description: 'old turn',
      occurred_at: new Date(messageCreatedAtMs - 60_000).toISOString(),
      metadata: { chat_id: 'c1' },
    };
    expect(isMemoryEventForMessage(stalePayload, 'c1', messageCreatedAtMs)).toBe(false);

    const freshPayload = {
      kind: 'extract',
      status: 'success',
      description: 'current turn',
      occurred_at: new Date(messageCreatedAtMs + 1000).toISOString(),
      metadata: { chat_id: 'c1' },
    };
    expect(isMemoryEventForMessage(freshPayload, 'c1', messageCreatedAtMs)).toBe(true);
  });

  it('filters trace events older than message createdAt', () => {
    const messageCreatedAtMs = 1_700_000_000_000;
    expect(
      isTraceMemoryEventForMessage(
        { status: 'success', summary: 'old', timestamp: messageCreatedAtMs / 1000 - 60 },
        messageCreatedAtMs,
      ),
    ).toBe(false);
    expect(
      isTraceMemoryEventForMessage(
        { status: 'success', summary: 'fresh', timestamp: messageCreatedAtMs / 1000 + 1 },
        messageCreatedAtMs,
      ),
    ).toBe(true);
  });

  it('rejects SSE and trace events without timestamps when scoping to a message', () => {
    const messageCreatedAtMs = 1_700_000_000_000;
    expect(
      isMemoryEventForMessage(
        { kind: 'extract', status: 'success', metadata: { chat_id: 'c1' } },
        'c1',
        messageCreatedAtMs,
      ),
    ).toBe(false);
    expect(
      isTraceMemoryEventForMessage({ status: 'success', summary: 'no ts' }, messageCreatedAtMs),
    ).toBe(false);
  });

  it('resolveMessageCreatedAtMs accepts ISO strings and Date objects', () => {
    const iso = '2026-08-05T03:48:00.000Z';
    const fromIso = resolveMessageCreatedAtMs(iso);
    const fromDate = resolveMessageCreatedAtMs(new Date(iso));
    expect(fromIso).toBe(Date.parse(iso));
    expect(fromDate).toBe(fromIso);
    expect(resolveMessageCreatedAtMs(new Date(Number.NaN))).toBeUndefined();
    expect(resolveMessageCreatedAtMs(undefined)).toBeUndefined();
  });
});
