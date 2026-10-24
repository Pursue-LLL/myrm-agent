/**
 * [INPUT]
 * @/store/chat/clarificationState::normalizeHydratedClarification (POS: pending clarify restore)
 * @/components/features/message-box/memoryLifecyclePhases::resolveMessageCreatedAtMs (POS: message timestamp)
 *
 * [OUTPUT]
 * parseMessages: Normalize persisted API messages into store Message objects (metadata, cited memory refs,
 *   system notice marker).
 *
 * [POS]
 * Pure hydration helpers for chat history; no store access.
 */

import type { Message } from '@/store/chat/types';
import { normalizeHydratedClarification } from '@/store/chat/clarificationState';
import { resolveMessageCreatedAtMs } from '@/components/features/message-box/memoryLifecyclePhases';

/** Metadata keys the server sets on assistant rows it appends itself (its `SYSTEM_NOTICE_EXTRA_KEYS`). */
const SYSTEM_NOTICE_METADATA_KEYS = ['background_job', 'voice_background_task'] as const;

export function parseMessages(raw: Message[]): Message[] {
  return raw.map((msg) => {
    const rawRecord = msg as Record<string, unknown>;
    const metadata =
      typeof rawRecord.metadata === 'string'
        ? (JSON.parse(rawRecord.metadata) as Record<string, unknown>)
        : ((rawRecord.metadata as Record<string, unknown> | undefined) ?? {});

    const citedMemoryIds = normalizeStringArray(metadata.citedMemoryIds ?? rawRecord.citedMemoryIds);
    const citedMemoryRefs = normalizeCitedMemoryRefs(metadata.citedMemoryRefs ?? rawRecord.citedMemoryRefs);
    const turnLoadedSkills = normalizeTurnLoadedSkills(
      metadata.turnLoadedSkills ?? metadata.turn_loaded_skills ?? rawRecord.turnLoadedSkills,
    );

    const createdAtMs = resolveMessageCreatedAtMs(
      (msg.createdAt ?? rawRecord.created_at ?? rawRecord.createdAt) as Date | string | number | undefined,
    );

    const parsed = {
      ...msg,
      ...metadata,
      createdAt: createdAtMs !== null && createdAtMs !== undefined ? new Date(createdAtMs) : new Date(),
      ...(citedMemoryIds ? { citedMemoryIds } : {}),
      ...(citedMemoryRefs ? { citedMemoryRefs } : {}),
      ...(turnLoadedSkills ? { turnLoadedSkills } : {}),
    } as Message;

    const persistedRequestMessageId = metadata.request_message_id;
    if (typeof persistedRequestMessageId === 'string' && persistedRequestMessageId.length > 0) {
      parsed.requestMessageId = persistedRequestMessageId;
    }

    if (SYSTEM_NOTICE_METADATA_KEYS.some((key) => metadata[key] === true)) {
      parsed.isSystemNotice = true;
    }

    if (parsed.clarification) {
      parsed.clarification = normalizeHydratedClarification(parsed.clarification);
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

function normalizeTurnLoadedSkills(value: unknown): Message['turnLoadedSkills'] {
  if (!Array.isArray(value)) {
    return undefined;
  }
  const rows: NonNullable<Message['turnLoadedSkills']> = [];
  for (const item of value) {
    if (typeof item !== 'object' || item === null) {
      continue;
    }
    const record = item as Record<string, unknown>;
    const name = record.name;
    if (typeof name !== 'string' || !name.trim()) {
      continue;
    }
    const idRaw = record.id;
    const id = typeof idRaw === 'string' && idRaw.trim() ? idRaw.trim() : name.trim();
    const hashRaw = record.content_hash ?? record.contentHash;
    rows.push({
      name: name.trim(),
      id,
      content_hash: typeof hashRaw === 'string' ? hashRaw : undefined,
      version: typeof record.version === 'string' ? record.version : undefined,
      partial: Boolean(record.partial),
    });
  }
  return rows.length > 0 ? rows : undefined;
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
