import type { TeammateMessageEntry } from '@/store/chat/useSubagentStore';

type TeammateMessageRow = {
  message_id?: string | number;
  from_task_id?: string | number;
  to_task_id?: string | number;
  body?: string | number;
  created_at?: string | number;
};

export function normalizeTeammateEntry(row: TeammateMessageRow): TeammateMessageEntry {
  let created = Number(row.created_at ?? 0);
  if (created > 1e12) {
    created = Math.floor(created / 1000);
  }
  return {
    message_id: typeof row.message_id === 'string' ? row.message_id : undefined,
    from_task_id: String(row.from_task_id),
    to_task_id: String(row.to_task_id),
    body: String(row.body ?? ''),
    created_at: created,
  };
}

export function mergeTeammateEntries(
  existing: TeammateMessageEntry[] | undefined,
  incoming: TeammateMessageEntry[],
): TeammateMessageEntry[] {
  const byKey = new Map<string, TeammateMessageEntry>();
  for (const entry of [...(existing ?? []), ...incoming]) {
    const key = entry.message_id ?? `${entry.created_at}-${entry.from_task_id}-${entry.to_task_id}-${entry.body}`;
    byKey.set(key, entry);
  }
  return Array.from(byKey.values()).slice(-20);
}
