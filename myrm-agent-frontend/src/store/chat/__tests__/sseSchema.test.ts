import { describe, expect, it } from 'vitest';
import { AgentEventType } from '../types';
import {
  HARNESS_AGENT_EVENT_TYPE_VALUES,
  HARNESS_SSE_EVENT_ALIASES,
  KNOWN_SSE_EVENT_TYPE_VALUES,
  isKnownSseEventType,
  normalizeSseEventType,
} from '../knownSseEventTypes';
import { parseSseEnvelope } from '../schema';

describe('sse schema', () => {
  it('includes every frontend AgentEventType value in the known set', () => {
    for (const value of Object.values(AgentEventType)) {
      expect(KNOWN_SSE_EVENT_TYPE_VALUES).toContain(value);
    }
  });

  it('includes every harness AgentEventType value in the known set', () => {
    for (const value of HARNESS_AGENT_EVENT_TYPE_VALUES) {
      expect(KNOWN_SSE_EVENT_TYPE_VALUES).toContain(value);
    }
  });

  it('normalizes harness cancelled to agent_cancelled', () => {
    expect(normalizeSseEventType('cancelled')).toBe(AgentEventType.AGENT_CANCELLED);
    expect(HARNESS_SSE_EVENT_ALIASES.cancelled).toBe(AgentEventType.AGENT_CANCELLED);
  });

  it('parseSseEnvelope rejects unknown type', () => {
    expect(
      parseSseEnvelope({ type: 'totally_unknown_event', messageId: 'm1' }),
    ).toBeNull();
  });

  it('parseSseEnvelope accepts FILE_DIFF and normalizes cancelled', () => {
    const diff = parseSseEnvelope({
      type: AgentEventType.FILE_DIFF,
      messageId: 'm1',
      file_path: '/tmp/a',
      diff: '+',
    });
    expect(diff).not.toBeNull();
    expect(diff?.type).toBe(AgentEventType.FILE_DIFF);

    const cancelled = parseSseEnvelope({ type: 'cancelled', messageId: 'm1' });
    expect(cancelled?.type).toBe(AgentEventType.AGENT_CANCELLED);
  });

  it('isKnownSseEventType covers harness pass-through without alias', () => {
    expect(isKnownSseEventType('approval_intercepted')).toBe(true);
  });
});
