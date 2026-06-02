/**
 * [INPUT]
 * @/store/chat/types::CitedMemoryReference (POS: Chat state and SSE event type definitions)
 *
 * [OUTPUT]
 * isMemoryRecallToolName: Detects memory citation-capable tool names.
 * normalizeCitedMemoryReferences: Converts raw SSE/metadata payloads into typed citation refs.
 * mergeCitedMemoryReferences: Deduplicates and merges citation refs by memory ID.
 *
 * [POS]
 * Chat memory citation normalization helpers. Keeps stream handling free of raw payload parsing details.
 */

import type { CitedMemoryReference } from '@/store/chat/types';

export type MemoryRecallToolName = 'memory_recall' | 'memory_recall_tool';

const MEMORY_RECALL_TOOL_NAMES: readonly MemoryRecallToolName[] = ['memory_recall', 'memory_recall_tool'];

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null && !Array.isArray(value);

const optionalString = (value: unknown): string | undefined => (typeof value === 'string' && value ? value : undefined);

const optionalNumber = (value: unknown): number | undefined => (typeof value === 'number' ? value : undefined);

const optionalStringArray = (value: unknown): string[] | undefined => {
  if (!Array.isArray(value)) return undefined;
  const items = value.filter((item): item is string => typeof item === 'string' && item.length > 0);
  return items.length ? items : undefined;
};

export const isMemoryRecallToolName = (value: unknown): value is MemoryRecallToolName =>
  typeof value === 'string' && (MEMORY_RECALL_TOOL_NAMES as readonly string[]).includes(value);

export const normalizeCitedMemoryReferences = (value: unknown): CitedMemoryReference[] => {
  if (!Array.isArray(value)) return [];

  const refs: CitedMemoryReference[] = [];
  const seen = new Set<string>();

  for (const item of value) {
    if (!isRecord(item)) continue;
    const id = optionalString(item.id);
    if (!id || seen.has(id)) continue;

    refs.push({
      id,
      memoryType: optionalString(item.memory_type) ?? optionalString(item.memoryType),
      content: optionalString(item.content),
      score: optionalNumber(item.score),
      createdAt: optionalString(item.created_at) ?? optionalString(item.createdAt),
      primaryNamespace: optionalString(item.primary_namespace) ?? optionalString(item.primaryNamespace),
      namespaces: optionalStringArray(item.namespaces),
      sourceChatId: optionalString(item.source_chat_id) ?? optionalString(item.sourceChatId),
      sourceMessageId: optionalString(item.source_message_id) ?? optionalString(item.sourceMessageId),
    });
    seen.add(id);
  }

  return refs;
};

export const mergeCitedMemoryReferences = (
  existing: CitedMemoryReference[] | undefined,
  incoming: CitedMemoryReference[],
): CitedMemoryReference[] => {
  if (!incoming.length) return existing ?? [];

  const byId = new Map<string, CitedMemoryReference>();
  for (const ref of existing ?? []) byId.set(ref.id, ref);
  for (const ref of incoming) byId.set(ref.id, { ...byId.get(ref.id), ...ref });
  return [...byId.values()];
};
