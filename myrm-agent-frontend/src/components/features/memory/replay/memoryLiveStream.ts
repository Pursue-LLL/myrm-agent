/**
 * [INPUT]
 * @/services/memoryCommandCenter::MemoryCommandTimelineEvent (POS: Frontend Personal Brain Command Center client)
 *
 * [OUTPUT]
 * isMemoryTimelineEvent, resolveReplaySessionId, mergeLiveStreamEvents: Live Memory Stream SSE helpers with RECALL burst coalescing.
 *
 * [POS]
 * Command Center 实时记忆流纯函数。校验 SSE payload、解析 replay 深链 session_id、合并增量事件。
 */

import type { MemoryCommandTimelineEvent } from '@/services/memoryCommandCenter';

export const LIVE_STREAM_LIMIT = 50;

export const isMemoryTimelineEvent = (value: unknown): value is MemoryCommandTimelineEvent => {
  if (!value || typeof value !== 'object') return false;
  const candidate = value as Partial<MemoryCommandTimelineEvent>;
  return (
    typeof candidate.id === 'string' &&
    typeof candidate.kind === 'string' &&
    typeof candidate.status === 'string' &&
    typeof candidate.occurred_at === 'string' &&
    typeof candidate.title === 'string' &&
    typeof candidate.description === 'string' &&
    typeof candidate.source === 'string'
  );
};

export const resolveReplaySessionId = (event: MemoryCommandTimelineEvent): string | null => {
  const chatId = event.metadata?.chat_id;
  if (typeof chatId === 'string' && chatId.length > 0) return chatId;
  if (event.target_kind === 'chat' && typeof event.target_id === 'string' && event.target_id.length > 0) {
    return event.target_id;
  }
  return null;
};

export const mergeLiveStreamEvents = (
  previous: MemoryCommandTimelineEvent[],
  incoming: MemoryCommandTimelineEvent,
  limit: number = LIVE_STREAM_LIMIT,
): MemoryCommandTimelineEvent[] => {
  if (previous.some((item) => item.id === incoming.id)) return previous;

  const messageId = incoming.metadata?.message_id;
  if (incoming.kind === 'recall' && typeof messageId === 'string' && messageId.length > 0) {
    const head = previous[0];
    if (head?.kind === 'recall' && head.metadata?.message_id === messageId) {
      const stepCount = Number(head.metadata?.live_stream_step_count ?? 1) + 1;
      const merged: MemoryCommandTimelineEvent = {
        ...incoming,
        id: head.id,
        description: incoming.description,
        metadata: {
          ...incoming.metadata,
          live_stream_step_count: stepCount,
        },
      };
      return [merged, ...previous.slice(1)].slice(0, limit);
    }
  }

  return [incoming, ...previous].slice(0, limit);
};
