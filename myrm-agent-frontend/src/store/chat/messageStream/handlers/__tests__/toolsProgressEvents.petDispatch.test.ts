/**
 * Tests for pet-status-event CustomEvent dispatches in toolsProgressEvents handler.
 * Covers: APPROVAL_REQUIRED, CLARIFICATION_REQUIRED, TOOL_APPROVAL_REQUEST, APPROVAL_PROCESSED.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/lib/approval/buildToolApprovalRequest', () => ({
  buildToolApprovalRequest: vi.fn(() => ({ id: 'mock-req' })),
}));

vi.mock('./handlerDeps', () => {
  const AgentEventType = {
    TOOL_PROGRESS: 'tool_progress',
    TOOL_HEARTBEAT: 'tool_heartbeat',
    TASKS_STEPS: 'tasks_steps',
    SOURCES: 'sources',
    APPROVAL_REQUIRED: 'approval_required',
    CLARIFICATION_REQUIRED: 'clarification_required',
    TOOL_APPROVAL_REQUEST: 'tool_approval_request',
    APPROVAL_PROCESSED: 'approval_processed',
    TOOLS_SNAPSHOT: 'tools_snapshot',
  } as const;

  return {
    AgentEventType,
    findAssistantMessageIndex: vi.fn(() => 0),
    useChatStore: {
      getState: vi.fn(() => ({ chatId: 'c1', actionMode: 'auto' })),
    },
    useToolApprovalStore: {
      getState: vi.fn(() => ({
        addRequest: vi.fn(),
        removeRequestsByMessageId: vi.fn(),
      })),
    },
    useToolsSnapshotStore: {
      getState: vi.fn(() => ({ setTools: vi.fn() })),
    },
    mapTaskStepStatus: vi.fn(() => 'success'),
    mergeMessageSources: vi.fn(),
  };
});

import { toolsProgressEvents } from '../toolsProgressEvents';
import type { StreamCtx } from '../../streamContext';

function makeCtx(eventType: string, extra: Record<string, unknown> = {}): StreamCtx {
  return {
    data: { type: eventType, messageId: 'msg-1', ...extra } as never,
    input: '',
    sources: undefined,
    added: true,
    recievedMessage: '',
    state: {} as never,
    actions: {
      setLoading: vi.fn(),
      setMessages: vi.fn(),
    } as never,
    files: [],
  };
}

describe('toolsProgressEvents pet-status-event dispatches', () => {
  const dispatchedEvents: CustomEvent[] = [];
  let origDispatch: typeof window.dispatchEvent;

  beforeEach(() => {
    vi.useFakeTimers();
    dispatchedEvents.length = 0;
    origDispatch = window.dispatchEvent;
    window.dispatchEvent = vi.fn((e: Event) => {
      if (e instanceof CustomEvent && e.type === 'pet-status-event') {
        dispatchedEvents.push(e);
      }
      return true;
    });
  });

  afterEach(() => {
    window.dispatchEvent = origDispatch;
    vi.useRealTimers();
  });

  it('APPROVAL_REQUIRED dispatches approval_waiting after microtask', async () => {
    const ctx = makeCtx('approval_required', { data: { type: 'manual', message: 'test' } });
    await toolsProgressEvents(ctx);

    expect(dispatchedEvents).toHaveLength(0);

    vi.advanceTimersByTime(0);
    expect(dispatchedEvents).toHaveLength(1);
    expect(dispatchedEvents[0].detail).toEqual({ step_key: 'approval_waiting' });
  });

  it('APPROVAL_REQUIRED calls setLoading(false) before pet dispatch', async () => {
    const ctx = makeCtx('approval_required', { data: { type: 'manual', message: 'test' } });
    await toolsProgressEvents(ctx);

    expect(ctx.actions.setLoading).toHaveBeenCalledWith(false);
  });

  it('CLARIFICATION_REQUIRED dispatches approval_waiting after microtask', async () => {
    const ctx = makeCtx('clarification_required', {
      data: {
        type: 'ask_question',
        form: {
          title: 'Question',
          questions: [{ id: 'q1', prompt: 'Pick one', options: [{ id: 'a', label: 'A' }] }],
        },
      },
    });
    await toolsProgressEvents(ctx);

    expect(dispatchedEvents).toHaveLength(0);

    vi.advanceTimersByTime(0);
    expect(dispatchedEvents).toHaveLength(1);
    expect(dispatchedEvents[0].detail).toEqual({ step_key: 'approval_waiting' });
  });

  it('CLARIFICATION_REQUIRED calls setLoading(false)', async () => {
    const ctx = makeCtx('clarification_required', {
      data: {
        type: 'ask_question',
        form: {
          title: 'Q',
          questions: [{ id: 'q1', prompt: 'Pick one', options: [{ id: 'a', label: 'A' }] }],
        },
      },
    });
    await toolsProgressEvents(ctx);
    expect(ctx.actions.setLoading).toHaveBeenCalledWith(false);
  });

  it('TOOL_APPROVAL_REQUEST dispatches approval_waiting synchronously', async () => {
    const ctx = makeCtx('tool_approval_request', {
      data: {
        actionRequests: [{ action: 'bash', args: { command: 'ls' } }],
        reviewConfigs: [null],
        extensions: { approval: { requestId: 'r1' } },
      },
    });
    await toolsProgressEvents(ctx);

    expect(dispatchedEvents).toHaveLength(1);
    expect(dispatchedEvents[0].detail).toEqual({ step_key: 'approval_waiting' });
  });

  it('APPROVAL_PROCESSED dispatches approval_released synchronously', async () => {
    const ctx = makeCtx('approval_processed', {});
    await toolsProgressEvents(ctx);

    expect(dispatchedEvents).toHaveLength(1);
    expect(dispatchedEvents[0].detail).toEqual({ step_key: 'approval_released' });
  });

  it('APPROVAL_PROCESSED calls removeRequestsByMessageId on store', async () => {
    const ctx = makeCtx('approval_processed', {});
    const result = await toolsProgressEvents(ctx);

    expect(result).not.toBeNull();
    expect(dispatchedEvents).toHaveLength(1);
    expect(dispatchedEvents[0].detail.step_key).toBe('approval_released');
  });

  it('returns done StreamTurn for all 4 event types', async () => {
    const types = [
      { type: 'approval_required', extra: { data: { type: 'manual' } } },
      { type: 'clarification_required', extra: { data: { title: 'Q', questions: [] } } },
      {
        type: 'tool_approval_request',
        extra: {
          data: {
            actionRequests: [{ action: 'bash', args: {} }],
            reviewConfigs: [null],
            extensions: { approval: { requestId: 'r1' } },
          },
        },
      },
      { type: 'approval_processed', extra: {} },
    ];

    for (const { type, extra } of types) {
      const ctx = makeCtx(type, extra);
      const result = await toolsProgressEvents(ctx);
      expect(result, `${type} should return StreamTurn`).not.toBeNull();
      expect(result).toHaveProperty('added');
      expect(result).toHaveProperty('recievedMessage');
    }
  });
});
