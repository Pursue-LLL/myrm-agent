import { describe, expect, it } from 'vitest';
import type { ExecutionTrace } from '@/services/statistics';
import type { Message } from '@/store/chat/types';
import {
  buildEventMarkers,
  buildMessageEvents,
  buildTimeline,
  computeTimelineBounds,
  findActiveEventIndex,
  isErrorLikeEvent,
  mergeMessages,
  normalizeApiMessage,
  snapToNearestEventTime,
} from '@/components/features/memory/replayTimeline';

const baseTrace: ExecutionTrace = {
  session_id: 'sess-1',
  metadata: { user_id: null, agent_id: null, task_type: null, trace_id: null },
  outcome: 'success',
  start_time: 1000,
  end_time: 1010,
  duration_ms: 10000,
  task_input: 'hello',
  output: 'done',
  tool_calls: [
    {
      sequence: 2,
      tool_name: 'bash',
      start_time: 1002,
      end_time: 1004,
      duration_ms: 2000,
      success: true,
      error: null,
    },
  ],
  llm_calls: [
    {
      sequence: 1,
      start_time: 1001,
      end_time: 1003,
      model_name: 'gpt-4o',
      prompt_preview: '[user] hi',
      message_count: 2,
      duration_ms: 2000,
      ttft_ms: 100,
      prompt_tokens: 10,
      completion_tokens: 5,
      total_tokens: 15,
    },
  ],
  errors: [],
  human_feedback: [],
  memory_events: [
    {
      id: 'mem-1',
      phase: 'write',
      status: 'success',
      timestamp: 1005,
      title: 'semantic',
      summary: 'stored fact',
      target_kind: 'chat',
      target_id: 'sess-1',
      influence_count: 0,
    },
  ],
  total_events: 5,
  total_tokens: 15,
};

function msg(role: 'user' | 'assistant', id: string, tsMs: number, content: string): Message {
  return {
    messageId: id,
    chatId: 'sess-1',
    role,
    content,
    createdAt: new Date(tsMs),
  } as Message;
}

describe('replayTimeline', () => {
  it('mergeMessages deduplicates by messageId and sorts by time', () => {
    const store = [msg('user', 'm1', 1000, 'a')];
    const remote = [msg('user', 'm1', 1000, 'a-full'), msg('assistant', 'm2', 2000, 'b')];
    const merged = mergeMessages(store, remote);
    expect(merged).toHaveLength(2);
    expect(merged[0].messageId).toBe('m1');
    expect(merged[0].content).toBe('a-full');
  });

  it('aligns assistant message after tool end in same turn', () => {
    const messages = [msg('user', 'u1', 1001000, 'run'), msg('assistant', 'a1', 1008000, 'done')];
    const events = buildMessageEvents(messages, baseTrace.tool_calls, 1000000);
    const assistant = events.find((e) => e.type === 'message' && e.data.role === 'assistant');
    expect(assistant?.time).toBe(1004000);
  });

  it('buildTimeline includes memory events', () => {
    const timeline = buildTimeline([], baseTrace);
    expect(timeline.some((e) => e.type === 'memory')).toBe(true);
    expect(timeline.some((e) => e.type === 'llm_call')).toBe(true);
  });

  it('snapToNearestEventTime picks closest event', () => {
    const timeline = buildTimeline([], baseTrace);
    const snapped = snapToNearestEventTime(timeline, 1002500);
    expect(timeline.map((e) => e.time)).toContain(snapped);
  });

  it('snapToNearestEventTime returns currentTime for empty timeline', () => {
    expect(snapToNearestEventTime([], 12345)).toBe(12345);
  });

  it('computeTimelineBounds falls back to trace times when timeline empty', () => {
    const emptyTrace: ExecutionTrace = {
      ...baseTrace,
      start_time: 5,
      end_time: 8,
      tool_calls: [],
      llm_calls: [],
      memory_events: [],
    };
    const bounds = computeTimelineBounds([], emptyTrace);
    expect(bounds.startTime).toBe(5000);
    expect(bounds.endTime).toBe(8000);
    expect(bounds.totalDuration).toBeGreaterThanOrEqual(1000);
  });

  it('findActiveEventIndex returns last event at or before currentTime', () => {
    const timeline = buildTimeline([], baseTrace);
    const idx = findActiveEventIndex(timeline, 1003500);
    expect(idx).toBeGreaterThanOrEqual(0);
    expect(timeline[idx].time).toBeLessThanOrEqual(1003500);
  });

  it('isErrorLikeEvent detects tool failure and rejected feedback', () => {
    const failedTool = {
      type: 'tool_end' as const,
      time: 1,
      data: { ...baseTrace.tool_calls[0], success: false },
    };
    const rejected = {
      type: 'human_feedback' as const,
      time: 2,
      data: { timestamp: 2, tool_name: null, action: null, approved: false },
    };
    expect(isErrorLikeEvent(failedTool)).toBe(true);
    expect(isErrorLikeEvent(rejected)).toBe(true);
    expect(isErrorLikeEvent({ type: 'message', time: 3, data: msg('user', 'u', 3, 'x') })).toBe(false);
  });

  it('buildEventMarkers deduplicates same-kind same-time markers', () => {
    const timeline = buildTimeline([], baseTrace);
    const { startTime, totalDuration } = computeTimelineBounds(timeline, baseTrace);
    const markers = buildEventMarkers(timeline, startTime, totalDuration);
    const keys = markers.map((m) => `${m.kind}-${m.time}`);
    expect(new Set(keys).size).toBe(keys.length);
    expect(markers.some((m) => m.kind === 'memory')).toBe(true);
  });

  it('normalizeApiMessage parses string metadata and preserves reasoning', () => {
    const raw = {
      messageId: 'm1',
      chatId: 'c1',
      role: 'assistant',
      content: 'hi',
      createdAt: '2024-01-01T00:00:00.000Z',
      metadata: JSON.stringify({ reasoning_content: 'think' }),
    } as unknown as Message;
    const normalized = normalizeApiMessage(raw);
    expect(normalized.reasoning).toBe('think');
    expect(normalized.createdAt).toBeInstanceOf(Date);
  });

  it('normalizeApiMessage keeps raw message when metadata JSON is invalid', () => {
    const raw = {
      messageId: 'm2',
      role: 'user',
      content: 'ok',
      createdAt: new Date(),
      metadata: '{bad json',
    } as unknown as Message;
    expect(normalizeApiMessage(raw).content).toBe('ok');
  });

  it('buildTimeline supports messages-only trace without tools or llm', () => {
    const messagesOnly: ExecutionTrace = {
      ...baseTrace,
      tool_calls: [],
      llm_calls: [],
      memory_events: [],
      errors: [],
      total_events: 0,
    };
    const messages = [msg('user', 'u1', 1001000, 'hello'), msg('assistant', 'a1', 1002000, 'world')];
    const timeline = buildTimeline(messages, messagesOnly);
    expect(timeline.filter((e) => e.type === 'message')).toHaveLength(2);
    expect(timeline.some((e) => e.type === 'tool_start')).toBe(false);
  });

  it('skips llm_call events when start_time is zero', () => {
    const trace: ExecutionTrace = {
      ...baseTrace,
      llm_calls: [{ ...baseTrace.llm_calls[0], start_time: 0 }],
    };
    const timeline = buildTimeline([], trace);
    expect(timeline.some((e) => e.type === 'llm_call')).toBe(false);
  });

  it('messageTimestamp returns null when createdAt missing', () => {
    const messages = [msg('user', 'u1', 1000, 'x'), { messageId: 'm0', role: 'user', content: 'y' } as Message];
    const events = buildMessageEvents(messages, [], 0);
    expect(events).toHaveLength(1);
  });
});
