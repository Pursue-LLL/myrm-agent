/**
 * [INPUT]
 * @/store/chat/clarificationState::normalizeHydratedClarification (POS: pending clarify restore)
 * @/store/chat/directoryRequestState::normalizeHydratedDirectoryRequest (POS: pending directory request restore)
 * @/components/features/message-box/memoryLifecyclePhases::resolveMessageCreatedAtMs (POS: message timestamp)
 *
 * [OUTPUT]
 * parseMessages: Normalize persisted API messages into store Message objects (metadata, TTSR, cited memory refs).
 *
 * [POS]
 * Pure hydration helpers for chat history; no store access.
 */

import type { Message } from '@/store/chat/types';
import { normalizeHydratedClarification } from '@/store/chat/clarificationState';
import { normalizeHydratedDirectoryRequest } from '@/store/chat/directoryRequestState';
import { resolveMessageCreatedAtMs } from '@/components/features/message-box/memoryLifecyclePhases';

export function parseMessages(raw: Message[]): Message[] {
  return raw.map((msg) => {
    const rawRecord = msg as Record<string, unknown>;
    const metadata =
      typeof rawRecord.metadata === 'string'
        ? (JSON.parse(rawRecord.metadata) as Record<string, unknown>)
        : ((rawRecord.metadata as Record<string, unknown> | undefined) ?? {});

    const citedMemoryIds = normalizeStringArray(metadata.citedMemoryIds ?? rawRecord.citedMemoryIds);
    const citedMemoryRefs = normalizeCitedMemoryRefs(metadata.citedMemoryRefs ?? rawRecord.citedMemoryRefs);

    const createdAtMs = resolveMessageCreatedAtMs(
      (msg.createdAt ?? rawRecord.created_at ?? rawRecord.createdAt) as Date | string | number | undefined,
    );

    const parsed = {
      ...msg,
      ...metadata,
      createdAt: createdAtMs !== null && createdAtMs !== undefined ? new Date(createdAtMs) : new Date(),
      ...(citedMemoryIds ? { citedMemoryIds } : {}),
      ...(citedMemoryRefs ? { citedMemoryRefs } : {}),
    } as Message;

    const persistedRequestMessageId = metadata.request_message_id;
    if (typeof persistedRequestMessageId === 'string' && persistedRequestMessageId.length > 0) {
      parsed.requestMessageId = persistedRequestMessageId;
    }

    if (parsed.clarification) {
      parsed.clarification = normalizeHydratedClarification(parsed.clarification);
    }

    if (parsed.directoryRequest) {
      parsed.directoryRequest = normalizeHydratedDirectoryRequest(parsed.directoryRequest);
    }

    if (!parsed.reasoning) {
      const persistedReasoning = metadata.reasoning_content;
      if (typeof persistedReasoning === 'string' && persistedReasoning.trim().length > 0) {
        parsed.reasoning = persistedReasoning;
      }
    }

    const rawBudget = metadata.contextBudget ?? metadata.context_budget;
    if (rawBudget && typeof rawBudget === 'object' && !parsed.contextBudget) {
      parsed.contextBudget = rawBudget as Message['contextBudget'];
    }

    const rawDeliverableTier = metadata.deliverableTier ?? metadata.deliverable_tier;
    if (rawDeliverableTier && typeof rawDeliverableTier === 'object' && !parsed.deliverableTier) {
      parsed.deliverableTier = rawDeliverableTier as Message['deliverableTier'];
    }

    const rawStagedArtifacts = metadata.stagedArtifacts ?? metadata.staged_artifacts;
    if (Array.isArray(rawStagedArtifacts) && !parsed.stagedArtifacts) {
      parsed.stagedArtifacts = rawStagedArtifacts as Message['stagedArtifacts'];
    }

    const rawTtsrInterventions = metadata.ttsrInterventions ?? metadata.ttsr_interventions;
    if (Array.isArray(rawTtsrInterventions)) {
      parsed.ttsrInterventions = normalizeTtsrInterventions(rawTtsrInterventions);
    }

    const rawAsyncUserMessages = metadata.asyncUserMessages ?? metadata.async_user_messages;
    if (Array.isArray(rawAsyncUserMessages) && !parsed.asyncUserMessages) {
      parsed.asyncUserMessages = rawAsyncUserMessages.map((item: Record<string, unknown>) => {
        const rawReplies = item.suggestedReplies ?? item.suggested_replies;
        const normalizedReplies = Array.isArray(rawReplies)
          ? rawReplies.filter((r): r is string => typeof r === 'string' && r.trim().length > 0)
          : undefined;
        return {
          callId: (item.callId ?? item.call_id ?? '') as string,
          message: (item.message ?? '') as string,
          category: (item.category ?? 'progress') as 'progress' | 'milestone' | 'question',
          recommendation: (item.recommendation ?? null) as string | null,
          suggested_replies: normalizedReplies,
          suggestedReplies: normalizedReplies,
          status: (item.status === 'resolved' ? 'resolved' : 'pending') as 'pending' | 'resolved',
          resolvedText: (item.resolvedText ?? item.resolved_text ?? null) as string | null,
        };
      });
    }

    return parsed;
  });
}

function normalizeStringArray(value: unknown): string[] | undefined {
  if (!Array.isArray(value)) {
    return undefined;
  }
  const ids = value.filter((item): item is string => typeof item === 'string' && item.length > 0);
  return ids.length > 0 ? ids : undefined;
}

function normalizeCitedMemoryRefs(value: unknown): Message['citedMemoryRefs'] {
  if (!Array.isArray(value)) {
    return undefined;
  }
  const refs = value.filter(
    (item): item is NonNullable<Message['citedMemoryRefs']>[number] =>
      typeof item === 'object' && item !== null && typeof (item as { id?: unknown }).id === 'string',
  );
  return refs.length > 0 ? refs : undefined;
}

function normalizeTtsrInterventions(value: unknown): Message['ttsrInterventions'] {
  if (!Array.isArray(value)) {
    return undefined;
  }
  const result: NonNullable<Message['ttsrInterventions']> = [];
  for (const item of value) {
    if (typeof item !== 'object' || item === null) {
      continue;
    }
    const record = item as Record<string, unknown>;
    const rawId = record.ruleId ?? record.rule_id;
    if (typeof rawId !== 'string' || !rawId.trim()) {
      continue;
    }
    const rawName = record.ruleName ?? record.rule_name;
    const ruleName = typeof rawName === 'string' && rawName.trim() ? rawName.trim() : rawId.trim();
    const reminder = typeof record.reminder === 'string' ? record.reminder : '';
    const rawTarget = record.target;
    const target =
      rawTarget === 'assistant' || rawTarget === 'thinking' || rawTarget === 'tool_args' || rawTarget === 'all'
        ? rawTarget
        : undefined;
    const rawRetry = record.retryCount ?? record.retry_count;
    const retryCount = typeof rawRetry === 'number' && rawRetry >= 0 ? rawRetry : 1;
    const rawMax = record.maxRetries ?? record.max_retries;
    const maxRetries = typeof rawMax === 'number' && rawMax >= 0 ? rawMax : 2;

    result.push({
      ruleId: rawId.trim(),
      ruleName,
      reminder,
      target,
      retryCount,
      maxRetries,
      timestamp: record.timestamp ? (record.timestamp as string | number | Date) : undefined,
    });
  }
  return result.length > 0 ? result : undefined;
}
