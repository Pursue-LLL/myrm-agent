/**
 * Stream handlers against the real (immutable) chat store.
 *
 * A sent turn hands its stream the store as it was before the turn; the turn's own assistant message only enters
 * the store through the stream's setMessages. A handler that reads message state from that start-of-turn snapshot
 * therefore never finds the running turn's message and silently does nothing, which hand-built mutable test states
 * cannot reveal. Every case here streams a whole turn through the real store.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';

import useChatStore from '@/store/useChatStore';
import { AdaptiveScheduler } from '../adaptiveScheduler';
import { handleMessageStream, type StreamHandlerActions, type StreamHandlerState } from '../messageStreamHandler';
import { AgentEventType, type AgentStreamEvent, type Message, type ProgressItem } from '../types';

const processSuggestions = vi.hoisted(() => vi.fn(async () => undefined));

// A finished turn also notifies, plays its sound and refreshes the workspace; none of that is under test here.
vi.mock('@/services/notification', () => ({ notificationService: { notify: vi.fn() } }));
vi.mock('@/lib/utils/completionSound', () => ({
  playCompletionSound: vi.fn(() => false),
  dispatchPetSurfaceAwayCompletion: vi.fn(),
}));
vi.mock('@/lib/progression/tryMarkMilestone', () => ({ tryMarkMilestone: vi.fn() }));
vi.mock('@/services/chat', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/services/chat')>()),
  getChatDetail: vi.fn(async () => ({ chat: {} })),
}));

const MESSAGE_ID = 'assistant-live-store';
const CHAT_ID = 'chat-live-store';
const BATCH_ID = 'a1b2c3d4-e5f6-4789-a012-3456789abcde';

function stepEvent(toolName: string, toolCallId: string): AgentStreamEvent {
  return {
    type: AgentEventType.TASKS_STEPS,
    messageId: MESSAGE_ID,
    step_key: `${toolName}_tool`,
    tool_name: toolName,
    tool_call_id: toolCallId,
    data: [{ text: toolName }],
  };
}

function toolEnd(toolName: string, extra: Record<string, unknown> = {}): AgentStreamEvent {
  return { type: AgentEventType.TOOL_END, messageId: MESSAGE_ID, tool_name: toolName, ...extra } as AgentStreamEvent;
}

/** Streams `events` the way a sent turn does and returns the assistant message the store ends up holding. */
async function streamTurn(events: AgentStreamEvent[]): Promise<Message> {
  const before = useChatStore.getState();
  const state: StreamHandlerState = {
    chatId: CHAT_ID,
    messages: before.messages,
    messageAppeared: false,
    loading: true,
    scheduler: new AdaptiveScheduler(),
  };
  const actions: StreamHandlerActions = {
    setMessages: (updater) => useChatStore.setState((draft) => updater(draft)),
    setMessageAppeared: () => undefined,
    setLoading: () => undefined,
    _processSuggestions: processSuggestions,
    scheduleAutoSave: () => undefined,
  };

  let turn = { added: false, recievedMessage: '' };
  for (const event of events) {
    turn = await handleMessageStream(event, '', undefined, turn.added, turn.recievedMessage, state, actions);
  }
  return useChatStore.getState().messages[0];
}

async function lastStep(events: AgentStreamEvent[]): Promise<ProgressItem> {
  const steps = (await streamTurn(events)).progressSteps ?? [];
  return steps[steps.length - 1];
}

describe('stream handlers write through the live store', () => {
  beforeEach(() => {
    useChatStore.setState({ chatId: CHAT_ID, messages: [] });
    processSuggestions.mockClear();
  });

  describe('tool_end', () => {
    it('links the committed skill_manage batch to the step that saved the skill', async () => {
      const step = await lastStep([
        stepEvent('skill_manage_tool', 'call-1'),
        toolEnd('skill_manage_tool', { skill_mutation_batch_id: BATCH_ID }),
      ]);

      expect(step.skill_mutation_batch_id).toBe(BATCH_ID);
    });

    it('marks the finished step successful with its duration', async () => {
      const step = await lastStep([
        stepEvent('file_read_tool', 'call-1'),
        toolEnd('file_read_tool', { duration_ms: 42 }),
      ]);

      expect(step).toMatchObject({ duration_ms: 42, status: 'success' });
    });

    it('turns a kanban task the board refused into a failed step', async () => {
      const step = await lastStep([
        stepEvent('kanban_add_task', 'call-1'),
        toolEnd('kanban_add_task', { duration_ms: 5, result: JSON.stringify({ error: ' no such board ' }) }),
      ]);

      expect(step).toMatchObject({ status: 'error', error: 'no such board' });
    });

    it('records the kanban task a successful call created', async () => {
      const task = { task_id: 't-1', board_id: 'b-1', title: 'Ship it' };
      const message = await streamTurn([
        stepEvent('kanban_add_task', 'call-1'),
        toolEnd('kanban_add_task', { result: { status: 'added', task } }),
      ]);

      expect(message.metadata?.kanban_tasks_created).toEqual([task]);
    });

    it('keeps the result of a cron job the call scheduled', async () => {
      const result = { status: 'success', job_id: 'job-1' };
      const message = await streamTurn([
        stepEvent('cron_manage', 'call-1'),
        toolEnd('cron_manage', { result: JSON.stringify(result) }),
      ]);

      expect(message.metadata?.cron_job_result).toEqual(result);
    });

    it('collects the memories a recall cited', async () => {
      const message = await streamTurn([
        stepEvent('memory_recall_tool', 'call-1'),
        toolEnd('memory_recall_tool', { duration_ms: 1, cited_memory_ids: ['mem-1', 'mem-1'] }),
      ]);

      expect(message.citedMemoryIds).toEqual(['mem-1']);
    });

    it('attaches the view of an MCP app tool', async () => {
      const message = await streamTurn([
        stepEvent('mcp_chart_tool', 'call-1'),
        toolEnd('mcp_chart_tool', { mcp_app: { resource_uri: 'ui://chart', server_name: 'charts' } }),
      ]);

      expect(message.mcpApps).toEqual([
        { resourceUri: 'ui://chart', serverName: 'charts', structuredContent: undefined, toolName: 'mcp_chart_tool' },
      ]);
    });
  });

  it('tool_failure marks the step failed with the error and its fault side', async () => {
    const step = await lastStep([
      stepEvent('bash_code_execute_tool', 'call-1'),
      {
        type: AgentEventType.TOOL_FAILURE,
        messageId: MESSAGE_ID,
        tool_name: 'bash_code_execute_tool',
        error: 'exit 1',
        fault_side: 'tool',
        duration_ms: 7,
      },
    ]);

    expect(step).toMatchObject({ status: 'error', error: 'exit 1', fault_side: 'tool', duration_ms: 7 });
  });

  it('tool_cancelled marks the step as cancelled with the reason', async () => {
    const step = await lastStep([
      stepEvent('bash_code_execute_tool', 'call-1'),
      {
        type: AgentEventType.TOOL_CANCELLED,
        messageId: MESSAGE_ID,
        tool_name: 'bash_code_execute_tool',
        error: 'cancelled',
        cancel_reason: 'user_cancelled',
      },
    ]);

    expect(step).toMatchObject({ status: 'warning', error: 'Cancelled by user' });
  });

  it('tool_stdout_chunk streams terminal output into the step', async () => {
    const stdoutChunk = (data: string): AgentStreamEvent => ({
      type: AgentEventType.TOOL_STDOUT_CHUNK,
      messageId: MESSAGE_ID,
      data,
    });

    const step = await lastStep([
      stepEvent('bash_code_execute_tool', 'call-1'),
      stdoutChunk('line 1\n'),
      stdoutChunk('line 2'),
    ]);

    expect(step.stdout).toBe('line 1\nline 2');
  });

  it('tool_evicted_ref files the stored output on the step that produced it', async () => {
    const message = await streamTurn([
      stepEvent('bash_code_execute_tool', 'call-1'),
      stepEvent('file_read_tool', 'call-2'),
      {
        type: AgentEventType.TOOL_EVICTED_REF,
        messageId: MESSAGE_ID,
        data: { evicted_ref: 'output_1.txt', tool_call_id: 'call-1', stored_chars: 4096 },
      },
    ]);
    const [producer, newest] = message.progressSteps ?? [];

    expect(producer).toMatchObject({ evicted_file_ref: 'output_1.txt', evicted_stored_chars: 4096 });
    expect(newest.evicted_file_ref).toBeUndefined();
  });

  it('tool_image_output attaches the image to the message', async () => {
    const message = await streamTurn([
      stepEvent('image_tool', 'call-1'),
      {
        type: AgentEventType.TOOL_IMAGE_OUTPUT,
        messageId: MESSAGE_ID,
        tool_name: 'image_tool',
        data: { url: 'https://example.com/chart.png', mime_type: 'image/png' },
      },
    ]);

    expect(message.toolImages).toEqual([
      { url: 'https://example.com/chart.png', mimeType: 'image/png', toolName: 'image_tool' },
    ]);
  });

  it('file_mutation_failed lists the files the turn could not write', async () => {
    const files = [{ path: 'notes.md', tool: 'file_write_tool', error_preview: 'read-only' }];
    const message = await streamTurn([
      stepEvent('file_write_tool', 'call-1'),
      { type: AgentEventType.FILE_MUTATION_FAILED, messageId: MESSAGE_ID, data: { files } },
    ]);

    expect(message.fileMutationFailures).toEqual(files);
  });

  it('workspace_merge_failed reports what could not be merged back', async () => {
    const errors = [{ message: 'conflict in notes.md' }];
    const message = await streamTurn([
      stepEvent('file_write_tool', 'call-1'),
      {
        type: AgentEventType.WORKSPACE_MERGE_FAILED,
        messageId: MESSAGE_ID,
        data: { errors, failed_count: 3, truncated: 1 },
      },
    ]);

    expect(message).toMatchObject({
      workspaceMergeFailures: errors,
      workspaceMergeFailedCount: 3,
      workspaceMergeTruncated: 1,
    });
  });

  it('message_end hands the finished answer to the follow-up suggestions', async () => {
    await streamTurn([
      stepEvent('file_read_tool', 'call-1'),
      { type: AgentEventType.MESSAGE, messageId: MESSAGE_ID, data: 'The answer.' },
      { type: AgentEventType.MESSAGE_END, messageId: MESSAGE_ID },
    ]);

    await vi.waitFor(() => expect(processSuggestions).toHaveBeenCalledTimes(1));
    expect(processSuggestions).toHaveBeenCalledWith(
      expect.objectContaining({ messageId: MESSAGE_ID, role: 'assistant', content: 'The answer.' }),
    );
  });
});
