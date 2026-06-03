import { describe, expect, it } from 'vitest';
import type { MemoryCommandTimelineEvent } from '@/services/memoryCommandCenter';
import {
  isMemoryTimelineEvent,
  mergeLiveStreamEvents,
  resolveReplaySessionId,
} from '@/components/features/memory/memoryLiveStream';

const baseEvent: MemoryCommandTimelineEvent = {
  id: 'evt-1',
  kind: 'recall',
  status: 'success',
  occurred_at: '2026-05-21T10:00:00.000Z',
  title: 'semantic',
  description: 'Recalled memories',
  source: 'memory_retrieval_trace',
  influence_count: 0,
  metadata: { chat_id: 'chat-abc' },
};

describe('memoryLiveStream', () => {
  it('validates timeline event shape', () => {
    expect(isMemoryTimelineEvent(baseEvent)).toBe(true);
    expect(isMemoryTimelineEvent({ id: 'x' })).toBe(false);
  });

  it('resolves replay session from metadata.chat_id', () => {
    expect(resolveReplaySessionId(baseEvent)).toBe('chat-abc');
  });

  it('resolves replay session from target_kind chat', () => {
    expect(
      resolveReplaySessionId({
        ...baseEvent,
        metadata: {},
        target_kind: 'chat',
        target_id: 'chat-target',
      }),
    ).toBe('chat-target');
  });

  it('mergeLiveStreamEvents prepends and deduplicates', () => {
    const next = { ...baseEvent, id: 'evt-2', description: 'new' };
    const merged = mergeLiveStreamEvents([baseEvent], next, 50);
    expect(merged).toHaveLength(2);
    expect(merged[0]?.id).toBe('evt-2');
    expect(mergeLiveStreamEvents(merged, next, 50)).toHaveLength(2);
  });

  it('mergeLiveStreamEvents coalesces recall bursts for the same message_id', () => {
    const first = {
      ...baseEvent,
      id: 'recall-1',
      metadata: { chat_id: 'chat-abc', message_id: 'msg-1', live_stream_step_count: 1 },
    };
    const second = {
      ...baseEvent,
      id: 'recall-2',
      description: 'rank phase',
      metadata: { chat_id: 'chat-abc', message_id: 'msg-1' },
    };
    const merged = mergeLiveStreamEvents([first], second, 50);
    expect(merged).toHaveLength(1);
    expect(merged[0]?.id).toBe('recall-1');
    expect(merged[0]?.metadata?.live_stream_step_count).toBe(2);
    expect(merged[0]?.description).toBe('rank phase');
  });

  it('mergeLiveStreamEvents does not coalesce recall for different message_id', () => {
    const first = {
      ...baseEvent,
      id: 'recall-1',
      metadata: { chat_id: 'chat-abc', message_id: 'msg-1' },
    };
    const second = {
      ...baseEvent,
      id: 'recall-2',
      metadata: { chat_id: 'chat-abc', message_id: 'msg-2' },
    };
    expect(mergeLiveStreamEvents([first], second, 50)).toHaveLength(2);
  });

  it('mergeLiveStreamEvents does not coalesce non-recall events', () => {
    const cite = { ...baseEvent, id: 'cite-1', kind: 'cite', metadata: { chat_id: 'chat-abc', message_id: 'msg-1' } };
    const recall = { ...baseEvent, id: 'recall-1', metadata: { chat_id: 'chat-abc', message_id: 'msg-1' } };
    expect(mergeLiveStreamEvents([cite], recall, 50)).toHaveLength(2);
  });
});
