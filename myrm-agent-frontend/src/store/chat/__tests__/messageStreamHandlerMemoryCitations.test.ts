import { describe, expect, it, vi } from 'vitest';
import { AdaptiveScheduler } from '../adaptiveScheduler';
import { handleMessageStream, type StreamHandlerActions, type StreamHandlerState } from '../messageStreamHandler';
import { AgentEventType, type AgentStreamEvent, type Message } from '../types';

vi.mock('@/lib/utils/toast', () => ({
  toast: {
    warning: vi.fn(),
  },
}));

const createActions = (): StreamHandlerActions => ({
  setMessages: () => undefined,
  setMessageAppeared: () => undefined,
  setLoading: () => undefined,
  _processSuggestions: async () => undefined,
  scheduleAutoSave: () => undefined,
});

const createStatefulActions = (state: StreamHandlerState): StreamHandlerActions => ({
  ...createActions(),
  setMessages: (updater) => updater(state),
});

describe('messageStreamHandler memory citations', () => {
  it('adds archive restore blocked progress from structured status events', async () => {
    const assistantMessage: Message = {
      messageId: 'assistant-1',
      chatId: 'chat-1',
      createdAt: new Date('2026-05-19T00:00:00Z'),
      content: '',
      role: 'assistant',
      progressSteps: [],
    };
    const state: StreamHandlerState = {
      messages: [assistantMessage],
      messageAppeared: false,
      loading: true,
      scheduler: new AdaptiveScheduler(),
    };

    await handleMessageStream(
      {
        type: AgentEventType.STATUS,
        messageId: 'assistant-1',
        step_key: 'archive_restore_blocked',
        tool_name: 'file_read_tool',
        status: 'warning',
        items: [{ text: 'Read a narrow line range.' }],
        data: {
          archive_restore_block: {
            message: 'Archived context restore blocked.',
            primary_restore_arg: '.context/chat/result.txt:1-200',
            recommended_ranges: ['.context/chat/result.txt:1-200', '.context/chat/result.txt:201-400'],
            restore_range_hints: [
              {
                range_arg: '.context/chat/result.txt:1-200',
                reason: 'fallback_chunk',
                start_line: 1,
                end_line: 200,
              },
            ],
          },
        },
      } satisfies AgentStreamEvent,
      '',
      undefined,
      false,
      '',
      state,
      createStatefulActions(state),
    );

    expect(state.messages[0].progressSteps).toEqual([
      {
        step_key: 'archive_restore_blocked',
        items: [{ text: 'Read a narrow line range.' }],
        tool_name: 'file_read_tool',
        status: 'warning',
        archive_restore_block: {
          message: 'Archived context restore blocked.',
          primary_restore_arg: '.context/chat/result.txt:1-200',
          recommended_ranges: ['.context/chat/result.txt:1-200', '.context/chat/result.txt:201-400'],
          restore_range_hints: [
            {
              range_arg: '.context/chat/result.txt:1-200',
              reason: 'fallback_chunk',
              start_line: 1,
              end_line: 200,
            },
          ],
        },
        archive_restore_actions: [
          {
            type: 'archive_restore',
            restoreArg: '.context/chat/result.txt:1-200',
          },
          {
            type: 'archive_restore',
            restoreArg: '.context/chat/result.txt:201-400',
          },
        ],
      },
    ]);
  });

  it('adds archive restore result progress from structured status events', async () => {
    const state: StreamHandlerState = {
      messages: [],
      messageAppeared: false,
      loading: true,
      scheduler: new AdaptiveScheduler(),
    };

    await handleMessageStream(
      {
        type: AgentEventType.STATUS,
        messageId: 'assistant-1',
        step_key: 'archive_restore_result',
        status: 'success',
        data: {
          archive_restore_result: {
            type: 'archive_restore_result',
            outcome: 'restored',
            archive_path: '.context/chat-1/compacted/result.txt',
            restore_arg: '.context/chat-1/compacted/result.txt:10-12',
            start_line: 10,
            end_line: 12,
            restored_line_count: 3,
            estimated_tokens: 120,
            restored_bytes: 512,
          },
        },
      } satisfies AgentStreamEvent,
      '',
      undefined,
      false,
      '',
      state,
      createStatefulActions(state),
    );

    expect(state.messages[0].progressSteps).toEqual([
      {
        step_key: 'archive_restore_result',
        items: [],
        tool_name: undefined,
        status: 'success',
        archive_restore_result: {
          type: 'archive_restore_result',
          outcome: 'restored',
          archive_path: '.context/chat-1/compacted/result.txt',
          restore_arg: '.context/chat-1/compacted/result.txt:10-12',
          start_line: 10,
          end_line: 12,
          restored_line_count: 3,
          estimated_tokens: 120,
          restored_bytes: 512,
        },
      },
    ]);
  });

  it('merges citations from the runtime memory_recall_tool alias', async () => {
    const assistantMessage: Message = {
      messageId: 'assistant-1',
      chatId: 'chat-1',
      createdAt: new Date('2026-04-30T00:00:00Z'),
      content: '',
      role: 'assistant',
      progressSteps: [],
    };
    const state: StreamHandlerState = {
      messages: [assistantMessage],
      messageAppeared: false,
      loading: true,
      scheduler: new AdaptiveScheduler(),
    };
    const event = {
      type: AgentEventType.TOOL_END,
      messageId: 'assistant-1',
      tool_name: 'memory_recall_tool',
      duration_ms: 12,
      cited_memory_ids: ['mem-1', 'mem-1'],
      cited_memory_refs: [
        {
          id: 'mem-1',
          memory_type: 'semantic',
          content: 'Shared Context marker.',
          primary_namespace: 'shared:customer-a',
        },
      ],
    } satisfies AgentStreamEvent;

    await handleMessageStream(event, '', undefined, false, '', state, createActions());

    expect(state.messages[0].citedMemoryIds).toEqual(['mem-1']);
    expect(state.messages[0].citedMemoryRefs).toEqual([
      {
        id: 'mem-1',
        memoryType: 'semantic',
        content: 'Shared Context marker.',
        primaryNamespace: 'shared:customer-a',
      },
    ]);
  });

  it('routes conversation_search sources to message sources without memory feedback ids', async () => {
    const assistantMessage: Message = {
      messageId: 'assistant-1',
      chatId: 'chat-1',
      createdAt: new Date('2026-04-30T00:00:00Z'),
      content: '',
      role: 'assistant',
      progressSteps: [],
      sources: [{ index: 1, type: 'web_search', url: 'https://example.com', title: 'Existing' }],
    };
    const state: StreamHandlerState = {
      messages: [assistantMessage],
      messageAppeared: false,
      loading: true,
      scheduler: new AdaptiveScheduler(),
    };

    await handleMessageStream(
      {
        type: AgentEventType.SOURCES,
        messageId: 'assistant-1',
        data: [
          {
            index: 1,
            type: 'conversation_history',
            conversation_id: 'chat-history',
            message_id: 'msg-1',
            title: 'Prior decision',
            source_key: 'conversation:chat-history:msg-1',
          },
        ],
      } satisfies AgentStreamEvent,
      '',
      undefined,
      false,
      '',
      state,
      createStatefulActions(state),
    );

    expect(state.messages[0].citedMemoryIds).toBeUndefined();
    expect(state.messages[0].sources).toEqual([
      { index: 1, type: 'web_search', url: 'https://example.com', title: 'Existing' },
      {
        index: 2,
        type: 'conversation_history',
        conversation_id: 'chat-history',
        message_id: 'msg-1',
        title: 'Prior decision',
        source_key: 'conversation:chat-history:msg-1',
      },
    ]);
  });
});
