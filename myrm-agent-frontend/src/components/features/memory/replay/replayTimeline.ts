/**
 * [INPUT]
 * - services/statistics::ExecutionTrace (POS: Session analytics trace types)
 * - store/chat/types::Message (POS: Chat message entity)
 *
 * [OUTPUT]
 * - buildTimeline, buildEventMarkers, computeTimelineBounds, snapToNearestEventTime
 * - mergeMessages, normalizeApiMessage, ReplayEvent union types
 *
 * [POS]
 * Pure timeline builders for Session Replay v2. Event-sourcing reconstruction
 * from trace + messages + memory events — no side effects, fully unit-testable.
 */

import type {
  ExecutionTrace,
  TraceToolCall,
  TraceLLMCall,
  TraceHumanFeedback,
  TraceError,
  TraceMemoryEvent,
} from '@/services/statistics';
import type { Message } from '@/store/chat/types';

export type ReplayEvent =
  | { type: 'tool_start'; time: number; data: TraceToolCall }
  | { type: 'tool_end'; time: number; data: TraceToolCall }
  | { type: 'llm_call'; time: number; data: TraceLLMCall }
  | { type: 'human_feedback'; time: number; data: TraceHumanFeedback }
  | { type: 'memory'; time: number; data: TraceMemoryEvent }
  | { type: 'error'; time: number; data: TraceError }
  | { type: 'message'; time: number; data: Message };

export type ReplayEventMarkerKind = 'tool' | 'llm' | 'message' | 'memory' | 'error';

export interface ReplayEventMarker {
  time: number;
  percent: number;
  kind: ReplayEventMarkerKind;
}

export function messageTimestamp(message: Message): number | null {
  if (!message.createdAt) return null;
  const ts = message.createdAt instanceof Date ? message.createdAt.getTime() : new Date(message.createdAt).getTime();
  return Number.isFinite(ts) ? ts : null;
}

export function messageReasoning(message: Message): string | undefined {
  if (message.reasoning) return message.reasoning;
  const legacy = message as Message & { reasoning_content?: string };
  return legacy.reasoning_content || undefined;
}

export function normalizeApiMessage(raw: Message): Message {
  const legacy = raw as Message & { reasoning_content?: string; metadata?: string | Record<string, unknown> };
  let parsed = raw;
  if (typeof legacy.metadata === 'string') {
    try {
      parsed = { ...raw, ...JSON.parse(legacy.metadata) };
    } catch {
      parsed = raw;
    }
  } else if (legacy.metadata && typeof legacy.metadata === 'object') {
    parsed = { ...raw, ...legacy.metadata };
  }
  const reasoning = messageReasoning(parsed);
  return {
    ...parsed,
    chatId: parsed.chatId ?? (raw as Message & { chatId?: string }).chatId ?? '',
    createdAt: parsed.createdAt instanceof Date ? parsed.createdAt : new Date(parsed.createdAt),
    reasoning,
  };
}

export function mergeMessages(storeMessages: Message[], remoteMessages: Message[]): Message[] {
  const byId = new Map<string, Message>();
  for (const m of [...storeMessages, ...remoteMessages]) {
    if (m.messageId) byId.set(m.messageId, m);
  }
  return [...byId.values()].sort((a, b) => (messageTimestamp(a) ?? 0) - (messageTimestamp(b) ?? 0));
}

/** Align assistant messages to the end of their tool turn, not stream-completion time. */
export function buildMessageEvents(
  messages: Message[],
  toolCalls: TraceToolCall[],
  sessionStartMs: number,
): ReplayEvent[] {
  const sorted = [...messages].sort((a, b) => (messageTimestamp(a) ?? 0) - (messageTimestamp(b) ?? 0));
  const events: ReplayEvent[] = [];

  for (let i = 0; i < sorted.length; i++) {
    const m = sorted[i];
    const baseTs = messageTimestamp(m);
    if (baseTs === null) continue;

    if (m.role === 'user') {
      events.push({ type: 'message', time: baseTs, data: m });
      continue;
    }

    const prevUser = sorted
      .slice(0, i)
      .reverse()
      .find((x) => x.role === 'user');
    const windowStart = prevUser ? (messageTimestamp(prevUser) ?? sessionStartMs) : sessionStartMs;
    const windowEnd = baseTs;

    const turnTools = toolCalls.filter((tc) => {
      const startMs = tc.start_time * 1000;
      return startMs >= windowStart && startMs <= windowEnd + 1000;
    });

    let displayTime = baseTs;
    if (turnTools.length > 0) {
      displayTime = turnTools.reduce((max, tc) => {
        const endMs = tc.end_time ? tc.end_time * 1000 : tc.start_time * 1000;
        return Math.max(max, endMs);
      }, windowStart);
    }

    events.push({ type: 'message', time: displayTime, data: m });
  }

  return events;
}

export function buildTimeline(messages: Message[], trace: ExecutionTrace): ReplayEvent[] {
  const sessionStartMs = trace.start_time > 0 ? trace.start_time * 1000 : 0;
  const events: ReplayEvent[] = buildMessageEvents(messages, trace.tool_calls, sessionStartMs);

  trace.tool_calls.forEach((tc) => {
    events.push({ type: 'tool_start', time: tc.start_time * 1000, data: tc });
    if (tc.end_time) events.push({ type: 'tool_end', time: tc.end_time * 1000, data: tc });
  });

  trace.llm_calls.forEach((lc) => {
    const startMs = lc.start_time > 0 ? lc.start_time * 1000 : 0;
    if (startMs > 0) {
      events.push({ type: 'llm_call', time: startMs, data: lc });
    }
  });

  trace.human_feedback.forEach((fb) => {
    events.push({ type: 'human_feedback', time: fb.timestamp * 1000, data: fb });
  });

  (trace.memory_events ?? []).forEach((me) => {
    events.push({ type: 'memory', time: me.timestamp * 1000, data: me });
  });

  trace.errors.forEach((err) => {
    events.push({ type: 'error', time: err.timestamp * 1000, data: err });
  });

  return events.sort((a, b) => a.time - b.time);
}

export function isErrorLikeEvent(event: ReplayEvent): boolean {
  if (event.type === 'error') return true;
  if (event.type === 'tool_end' && !event.data.success) return true;
  if (event.type === 'human_feedback' && event.data.approved === false) return true;
  return false;
}

export function computeTimelineBounds(
  timeline: ReplayEvent[],
  trace: ExecutionTrace,
): {
  startTime: number;
  endTime: number;
  totalDuration: number;
} {
  const startTime = timeline.length > 0 ? timeline[0].time : trace.start_time * 1000;
  const endTime =
    timeline.length > 0 ? timeline[timeline.length - 1].time : Math.max(trace.end_time * 1000, startTime + 1000);
  const totalDuration = Math.max(1000, endTime - startTime);
  return { startTime, endTime, totalDuration };
}

export function buildEventMarkers(
  timeline: ReplayEvent[],
  startTime: number,
  totalDuration: number,
): ReplayEventMarker[] {
  const seen = new Set<string>();
  const markers: ReplayEventMarker[] = [];

  for (const event of timeline) {
    let kind: ReplayEventMarkerKind | null = null;
    if (event.type === 'tool_start') kind = 'tool';
    else if (event.type === 'llm_call') kind = 'llm';
    else if (event.type === 'message') kind = 'message';
    else if (event.type === 'memory') kind = 'memory';
    else if (isErrorLikeEvent(event)) kind = 'error';
    if (!kind) continue;

    const key = `${kind}-${event.time}`;
    if (seen.has(key)) continue;
    seen.add(key);

    markers.push({
      kind,
      time: event.time,
      percent: ((event.time - startTime) / totalDuration) * 100,
    });
  }

  return markers;
}

export function snapToNearestEventTime(timeline: ReplayEvent[], currentTime: number): number {
  if (timeline.length === 0) return currentTime;
  let closest = timeline[0].time;
  let minDelta = Math.abs(currentTime - closest);
  for (const event of timeline) {
    const delta = Math.abs(currentTime - event.time);
    if (delta < minDelta) {
      minDelta = delta;
      closest = event.time;
    }
  }
  return closest;
}

export function findActiveEventIndex(timeline: ReplayEvent[], currentTime: number): number {
  let idx = -1;
  for (let i = 0; i < timeline.length; i++) {
    if (timeline[i].time <= currentTime) idx = i;
    else break;
  }
  return idx;
}
