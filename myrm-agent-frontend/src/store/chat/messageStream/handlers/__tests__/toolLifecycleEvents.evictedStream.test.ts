/**
 * tool_evicted_ref stream routing: stdout/stderr split onto the correct step.
 *
 * Failure-path bash emits one tool_evicted_ref per stream; the `stream` field
 * decides whether the ref lands on evicted_file_ref (stdout) or
 * evicted_stderr_file_ref (stderr). Legacy events without a stream default to
 * stdout so old clients keep working.
 */
import { describe, expect, it, vi } from 'vitest';

vi.mock('../handlerDeps', () => ({
  AgentEventType: { TOOL_EVICTED_REF: 'tool_evicted_ref' },
  findAssistantMessageIndex: vi.fn(
    (
      messages: Array<{ role: string; messageId: string }>,
      messageId: string,
    ) => messages.findIndex((msg) => msg.role === 'assistant' && msg.messageId === messageId),
  ),
}));

import { toolLifecycleEvents } from '../toolLifecycleEvents';
import { AdaptiveScheduler } from '../../../adaptiveScheduler';
import type { AgentStreamEvent } from '@/store/chat/types';
import type { ProgressItem } from '@/store/chat/types';
import type { StreamCtx, StreamTurn } from '../../streamContext';
import type { StreamHandlerActions, StreamHandlerState } from '../../types';

const MESSAGE_ID = 'msg-evict-1';

function makeStep(overrides: Record<string, unknown> = {}) {
  return {
    step_key: 'bash_code_execute_tool',
    tool_name: 'bash_code_execute_tool',
    tool_call_id: 'call_1',
    status: 'error',
    stdout: 'processed row 149',
    ...overrides,
  } as ProgressItem;
}

function createCtx(evictedPayload: Record<string, unknown>): StreamCtx {
  const state: StreamHandlerState = {
    messages: [
      {
        messageId: MESSAGE_ID,
        chatId: 'chat-evict',
        createdAt: new Date(),
        role: 'assistant',
        content: '',
        progressSteps: [makeStep()],
      },
    ],
    messageAppeared: false,
    loading: true,
    scheduler: new AdaptiveScheduler(),
  };
  const actions: StreamHandlerActions = {
    setMessages: (updater) => updater(state),
    setMessageAppeared: () => undefined,
    setLoading: () => undefined,
    _processSuggestions: async () => undefined,
    scheduleAutoSave: () => undefined,
  };

  return {
    data: {
      type: 'tool_evicted_ref',
      messageId: MESSAGE_ID,
      data: evictedPayload,
    } as unknown as AgentStreamEvent,
    input: '',
    sources: undefined,
    added: false,
    recievedMessage: '',
    state,
    actions,
    files: [],
  };
}

async function runAndStep(ctx: StreamCtx): Promise<ProgressItem> {
  const result: StreamTurn | null = await toolLifecycleEvents(ctx);
  expect(result).not.toBeNull();
  const step = ctx.state.messages[0]?.progressSteps?.[0];
  expect(step).toBeDefined();
  return step as ProgressItem;
}

describe('toolLifecycleEvents tool_evicted_ref stream routing', () => {
  it('routes stream=stderr to evicted_stderr_file_ref without touching stdout', async () => {
    const step = await runAndStep(
      createCtx({
        evicted_ref: 'output_stderr_1.txt',
        tool_name: 'bash_code_execute_tool',
        tool_call_id: 'call_1',
        stored_chars: 2048,
        total_lines: 100,
        storage_truncated: true,
        stream: 'stderr',
      }),
    );

    expect(step.evicted_stderr_file_ref).toBe('output_stderr_1.txt');
    expect(step.evicted_stderr_stored_chars).toBe(2048);
    expect(step.evicted_stderr_total_lines).toBe(100);
    expect(step.evicted_stderr_storage_truncated).toBe(true);
    expect(step.evicted_file_ref).toBeUndefined();
    expect(step.evicted_stored_chars).toBeUndefined();
  });

  it('routes stream=stdout to evicted_file_ref with metrics', async () => {
    const step = await runAndStep(
      createCtx({
        evicted_ref: 'output_stdout_1.txt',
        tool_name: 'bash_code_execute_tool',
        tool_call_id: 'call_1',
        stored_chars: 5120,
        total_lines: 240,
        stream: 'stdout',
      }),
    );

    expect(step.evicted_file_ref).toBe('output_stdout_1.txt');
    expect(step.evicted_stored_chars).toBe(5120);
    expect(step.evicted_total_lines).toBe(240);
    expect(step.evicted_stderr_file_ref).toBeUndefined();
  });

  it('treats a missing stream field as stdout for legacy events', async () => {
    const step = await runAndStep(
      createCtx({
        evicted_ref: 'output_legacy_1.txt',
        tool_name: 'bash_code_execute_tool',
        tool_call_id: 'call_1',
        total_lines: 10,
      }),
    );

    expect(step.evicted_file_ref).toBe('output_legacy_1.txt');
    expect(step.evicted_stderr_file_ref).toBeUndefined();
  });

  it('no-ops when the message is missing', async () => {
    const ctx = createCtx({
      evicted_ref: 'output_missing_1.txt',
      tool_name: 'bash_code_execute_tool',
      stream: 'stdout',
    });
    ctx.data = {
      type: 'tool_evicted_ref',
      messageId: 'msg-unknown',
      data: { evicted_ref: 'output_missing_1.txt' },
    } as unknown as AgentStreamEvent;

    const result = await toolLifecycleEvents(ctx);
    expect(result).not.toBeNull();
    expect(ctx.state.messages[0]?.progressSteps?.[0]?.evicted_file_ref).toBeUndefined();
  });

  it('no-ops when evicted_ref is missing', async () => {
    const step = await runAndStep(
      createCtx({
        tool_name: 'bash_code_execute_tool',
        stream: 'stderr',
      }),
    );

    expect(step.evicted_file_ref).toBeUndefined();
    expect(step.evicted_stderr_file_ref).toBeUndefined();
  });

  it('no-ops when the assistant message has no progress steps', async () => {
    const ctx = createCtx({
      evicted_ref: 'output_empty_1.txt',
      tool_name: 'bash_code_execute_tool',
      stream: 'stdout',
    });
    ctx.state.messages[0].progressSteps = [];

    const result = await toolLifecycleEvents(ctx);
    expect(result).not.toBeNull();
  });
});
