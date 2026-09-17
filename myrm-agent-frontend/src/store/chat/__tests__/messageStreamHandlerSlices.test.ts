import { describe, expect, it, vi } from 'vitest';
import { AdaptiveScheduler } from '../adaptiveScheduler';
import { handleMessageStream, type StreamHandlerActions, type StreamHandlerState } from '../messageStreamHandler';
import { AgentEventType, type Message } from '../types';

vi.mock('@/lib/utils/toast', () => ({
  toast: { warning: vi.fn() },
}));

const createStatefulActions = (state: StreamHandlerState): StreamHandlerActions => ({
  setMessages: (updater) => updater(state),
  setMessageAppeared: () => undefined,
  setLoading: () => undefined,
  _processSuggestions: async () => undefined,
  scheduleAutoSave: () => undefined,
});

describe('messageStreamHandler handler slices', () => {
  it('FILE_DIFF creates assistant row when missing and adds file_diff progress step', async () => {
    const userMessage: Message = {
      messageId: 'user-1',
      chatId: 'chat-1',
      createdAt: new Date('2026-06-04T00:00:00Z'),
      content: 'edit file',
      role: 'user',
    };
    const state: StreamHandlerState = {
      messages: [userMessage],
      messageAppeared: false,
      loading: true,
      scheduler: new AdaptiveScheduler(),
    };

    const turn = await handleMessageStream(
      {
        type: AgentEventType.FILE_DIFF,
        messageId: 'assistant-diff-1',
        data: {
          path: 'src/foo.ts',
          diff: '@@ -1 +1 @@\n+hello',
          is_new: false,
          lines_added: 1,
          lines_removed: 0,
          truncated: false,
        },
      },
      '',
      undefined,
      false,
      'partial',
      state,
      createStatefulActions(state),
    );

    expect(turn.added).toBe(true);
    expect(state.messages).toHaveLength(2);
    expect(state.messages[1]).toMatchObject({
      messageId: 'assistant-diff-1',
      role: 'assistant',
    });
    const steps = state.messages[1].progressSteps ?? [];
    expect(steps.some((s) => s.step_key === 'file_diff')).toBe(true);
  });

  it('TOOL_START clears accumulated stream text on ctx', async () => {
    const assistant: Message = {
      messageId: 'assistant-tool-1',
      chatId: 'chat-1',
      createdAt: new Date('2026-06-04T00:00:00Z'),
      content: '',
      role: 'assistant',
      progressSteps: [],
    };
    const state: StreamHandlerState = {
      messages: [assistant],
      messageAppeared: false,
      loading: true,
      scheduler: new AdaptiveScheduler(),
    };

    const turn = await handleMessageStream(
      {
        type: AgentEventType.TOOL_START,
        messageId: 'assistant-tool-1',
      },
      '',
      undefined,
      false,
      'chunk-before-tool',
      state,
      createStatefulActions(state),
    );

    expect(turn.recievedMessage).toBe('');
  });

  it('TOOL_END sets duration_ms on the last progress step', async () => {
    const assistant: Message = {
      messageId: 'assistant-tool-2',
      chatId: 'chat-1',
      createdAt: new Date('2026-06-04T00:00:00Z'),
      content: '',
      role: 'assistant',
      progressSteps: [
        {
          step_key: 'tool_run',
          tool_name: 'grep',
          items: [{ text: 'searching' }],
        },
      ],
    };
    const state: StreamHandlerState = {
      messages: [assistant],
      messageAppeared: false,
      loading: true,
      scheduler: new AdaptiveScheduler(),
    };

    await handleMessageStream(
      {
        type: AgentEventType.TOOL_END,
        messageId: 'assistant-tool-2',
        tool_name: 'grep',
        duration_ms: 420,
      },
      '',
      undefined,
      false,
      '',
      state,
      createStatefulActions(state),
    );

    const lastStep = state.messages[0].progressSteps?.[0];
    expect(lastStep?.duration_ms).toBe(420);
    expect(lastStep?.status).toBe('success');
  });

  it('TOOL_END marks kanban_add_task soft error on progress step instead of success', async () => {
    const assistant: Message = {
      messageId: 'assistant-kanban-err',
      chatId: 'chat-1',
      createdAt: new Date('2026-06-04T00:00:00Z'),
      content: '',
      role: 'assistant',
      progressSteps: [
        {
          step_key: 'kanban_add_task',
          tool_name: 'kanban_add_task',
          items: [{ text: 'adding task' }],
        },
      ],
    };
    const state: StreamHandlerState = {
      messages: [assistant],
      messageAppeared: false,
      loading: true,
      scheduler: new AdaptiveScheduler(),
    };

    await handleMessageStream(
      {
        type: AgentEventType.TOOL_END,
        messageId: 'assistant-kanban-err',
        tool_name: 'kanban_add_task',
        duration_ms: 88,
        result: JSON.stringify({ error: 'board_id is required' }),
      },
      '',
      undefined,
      false,
      '',
      state,
      createStatefulActions(state),
    );

    const lastStep = state.messages[0].progressSteps?.[0];
    expect(lastStep?.duration_ms).toBe(88);
    expect(lastStep?.status).toBe('error');
    expect(lastStep?.error).toBe('board_id is required');
    expect(state.messages[0].metadata?.kanban_tasks_created).toBeUndefined();
  });

  it('TOOL_END marks kanban_add_task soft error even without duration_ms', async () => {
    const assistant: Message = {
      messageId: 'assistant-kanban-err-no-dur',
      chatId: 'chat-1',
      createdAt: new Date('2026-06-04T00:00:00Z'),
      content: '',
      role: 'assistant',
      progressSteps: [{ step_key: 'kanban_add_task', tool_name: 'kanban_add_task' }],
    };
    const state: StreamHandlerState = {
      messages: [assistant],
      messageAppeared: false,
      loading: true,
      scheduler: new AdaptiveScheduler(),
    };

    await handleMessageStream(
      {
        type: AgentEventType.TOOL_END,
        messageId: 'assistant-kanban-err-no-dur',
        tool_name: 'kanban_add_task',
        duration_ms: 0,
        result: { error: 'Board board-1 not found' },
      },
      '',
      undefined,
      false,
      '',
      state,
      createStatefulActions(state),
    );

    const lastStep = state.messages[0].progressSteps?.[0];
    expect(lastStep?.status).toBe('error');
    expect(lastStep?.error).toBe('Board board-1 not found');
  });

  it('TOOL_END kanban_add_task success sets kanban_tasks_created metadata', async () => {
    const assistant: Message = {
      messageId: 'assistant-kanban-ok',
      chatId: 'chat-1',
      createdAt: new Date('2026-06-04T00:00:00Z'),
      content: '',
      role: 'assistant',
      progressSteps: [
        {
          step_key: 'kanban_add_task',
          tool_name: 'kanban_add_task',
          items: [{ text: 'adding task' }],
        },
      ],
    };
    const state: StreamHandlerState = {
      messages: [assistant],
      messageAppeared: false,
      loading: true,
      scheduler: new AdaptiveScheduler(),
    };

    await handleMessageStream(
      {
        type: AgentEventType.TOOL_END,
        messageId: 'assistant-kanban-ok',
        tool_name: 'kanban_add_task',
        duration_ms: 120,
        result: JSON.stringify({
          status: 'added',
          task: {
            task_id: 'task-abc',
            title: 'Weekly report',
            board_id: 'board-1',
          },
        }),
      },
      '',
      undefined,
      false,
      '',
      state,
      createStatefulActions(state),
    );

    const lastStep = state.messages[0].progressSteps?.[0];
    expect(lastStep?.duration_ms).toBe(120);
    expect(lastStep?.status).toBe('success');
    expect(state.messages[0].metadata?.kanban_tasks_created).toEqual([
      {
        task_id: 'task-abc',
        title: 'Weekly report',
        board_id: 'board-1',
      },
    ]);
  });

});
