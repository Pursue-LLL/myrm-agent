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
        tool_name: 'read_file',
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

  it('UI_UPDATE ui_artifact appends uiArtifacts on assistant message', async () => {
    const assistant: Message = {
      messageId: 'assistant-ui-1',
      chatId: 'chat-1',
      createdAt: new Date('2026-06-04T00:00:00Z'),
      content: '',
      role: 'assistant',
    };
    const state: StreamHandlerState = {
      messages: [assistant],
      messageAppeared: false,
      loading: true,
      scheduler: new AdaptiveScheduler(),
    };

    await handleMessageStream(
      {
        type: AgentEventType.UI_UPDATE,
        subtype: 'ui_artifact',
        messageId: 'assistant-ui-1',
        data: [
          {
            surface_id: 'form_deploy',
            title: '部署确认',
            components: [{ id: 't1', type: 'text', props: { text: '确认?' } }],
            root_ids: ['t1'],
            data: {},
            actions: [],
          },
        ],
      },
      '',
      undefined,
      false,
      'partial',
      state,
      createStatefulActions(state),
    );

    expect(state.messages[0].uiArtifacts).toHaveLength(1);
    expect(state.messages[0].uiArtifacts?.[0].title).toBe('部署确认');
    expect(state.messageAppeared).toBe(true);
  });

  it('UI_UPDATE data_update merges fields into existing uiArtifact', async () => {
    const assistant: Message = {
      messageId: 'assistant-ui-2',
      chatId: 'chat-1',
      createdAt: new Date('2026-06-04T00:00:00Z'),
      content: '',
      role: 'assistant',
      uiArtifacts: [
        {
          surface_id: 'form_1',
          title: 'Form',
          components: [],
          root_ids: [],
          data: { name: '', age: 0 },
          actions: [],
        },
      ],
    };
    const state: StreamHandlerState = {
      messages: [assistant],
      messageAppeared: true,
      loading: true,
      scheduler: new AdaptiveScheduler(),
    };

    await handleMessageStream(
      {
        type: AgentEventType.UI_UPDATE,
        subtype: 'data_update',
        messageId: 'assistant-ui-2',
        data: { surface_id: 'form_1', updates: { name: 'Alice', age: 30 } },
      },
      '',
      undefined,
      false,
      'partial',
      state,
      createStatefulActions(state),
    );

    expect(state.messages[0].uiArtifacts?.[0].data).toEqual({ name: 'Alice', age: 30 });
  });

  it('UI_UPDATE data_update deep-merges nested object fields', async () => {
    const assistant: Message = {
      messageId: 'assistant-ui-nested',
      chatId: 'chat-1',
      createdAt: new Date('2026-06-04T00:00:00Z'),
      content: '',
      role: 'assistant',
      uiArtifacts: [
        {
          surface_id: 'form_nested',
          title: 'Form',
          components: [],
          root_ids: [],
          data: { form: { note: '', env: 'staging' } },
          actions: [],
        },
      ],
    };
    const state: StreamHandlerState = {
      messages: [assistant],
      messageAppeared: true,
      loading: true,
      scheduler: new AdaptiveScheduler(),
    };

    await handleMessageStream(
      {
        type: AgentEventType.UI_UPDATE,
        subtype: 'data_update',
        messageId: 'assistant-ui-nested',
        data: { surface_id: 'form_nested', updates: { form: { note: 'done' } } },
      },
      '',
      undefined,
      false,
      'partial',
      state,
      createStatefulActions(state),
    );

    expect(state.messages[0].uiArtifacts?.[0].data).toEqual({
      form: { note: 'done', env: 'staging' },
    });
  });
});
