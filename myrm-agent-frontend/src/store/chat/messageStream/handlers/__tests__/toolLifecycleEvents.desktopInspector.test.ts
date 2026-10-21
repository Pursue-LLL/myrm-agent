import { beforeEach, describe, expect, it, vi } from 'vitest';

import { AgentEventType } from '@/store/chat/types';
import useDesktopInspectorStore from '@/store/useDesktopInspectorStore';
import useChatStore from '@/store/useChatStore';
import type { StreamHandlerActions, StreamHandlerState } from '../../types';
import type { StreamCtx } from '../../streamContext';
import { toolLifecycleEvents } from '../toolLifecycleEvents';

function buildToolEndCtx(toolName: string, streamChatId = 'chat-fg'): StreamCtx {
  const state: StreamHandlerState = {
    messages: [
      {
        messageId: 'msg-1',
        chatId: streamChatId,
        createdAt: new Date(),
        role: 'assistant',
        content: '',
        progressSteps: [{ step_key: 'desktop_tool', tool_name: toolName }],
      },
    ],
    messageAppeared: false,
    loading: false,
    scheduler: {} as StreamHandlerState['scheduler'],
  };
  const actions: StreamHandlerActions = {
    setMessages: vi.fn(),
    setMessageAppeared: vi.fn(),
    setLoading: vi.fn(),
    _processSuggestions: vi.fn(async () => undefined),
    scheduleAutoSave: vi.fn(),
  };

  return {
    data: {
      type: AgentEventType.TOOL_END,
      messageId: 'msg-1',
      tool_name: toolName,
    },
    input: '',
    sources: undefined,
    added: false,
    state,
    actions,
    recievedMessage: '',
    files: [],
  };
}

describe('toolLifecycleEvents desktop inspector TOOL_END fetch', () => {
  beforeEach(() => {
    useDesktopInspectorStore.getState().reset();
    useChatStore.setState({ chatId: undefined });
    vi.restoreAllMocks();
  });

  it('fetchSnapshot on desktop TOOL_END when stream chat matches foreground chat', async () => {
    useChatStore.setState({ chatId: 'chat-fg' });
    const fetchSnapshot = vi.fn(async () => true);
    useDesktopInspectorStore.setState({ fetchSnapshot });

    await toolLifecycleEvents(buildToolEndCtx('desktop_click_tool'));

    expect(fetchSnapshot).toHaveBeenCalledOnce();
  });

  it('skips fetchSnapshot when background stream chat differs from foreground chat', async () => {
    useChatStore.setState({ chatId: 'chat-fg' });
    const fetchSnapshot = vi.fn(async () => true);
    useDesktopInspectorStore.setState({ fetchSnapshot });

    await toolLifecycleEvents(buildToolEndCtx('desktop_click_tool', 'chat-bg'));

    expect(fetchSnapshot).not.toHaveBeenCalled();
  });

  it('skips fetchSnapshot for desktop_snapshot_tool', async () => {
    useChatStore.setState({ chatId: 'chat-fg' });
    const fetchSnapshot = vi.fn(async () => true);
    useDesktopInspectorStore.setState({ fetchSnapshot });

    await toolLifecycleEvents(buildToolEndCtx('desktop_snapshot_tool'));

    expect(fetchSnapshot).not.toHaveBeenCalled();
  });
});

describe('toolLifecycleEvents desktop inspector TOOL_START engagement', () => {
  beforeEach(() => {
    useDesktopInspectorStore.getState().reset();
    useChatStore.setState({ chatId: undefined });
    vi.restoreAllMocks();
  });

  function buildToolStartCtx(toolName: string): StreamCtx {
    const state: StreamHandlerState = {
      messages: [
        {
          messageId: 'msg-1',
          chatId: 'chat-fg',
          createdAt: new Date(),
          role: 'assistant',
          content: '',
          progressSteps: [],
        },
      ],
      messageAppeared: false,
      loading: false,
      scheduler: {} as StreamHandlerState['scheduler'],
    };
    const actions: StreamHandlerActions = {
      setMessages: vi.fn(),
      setMessageAppeared: vi.fn(),
      setLoading: vi.fn(),
      _processSuggestions: vi.fn(async () => undefined),
      scheduleAutoSave: vi.fn(),
    };

    return {
      data: {
        type: AgentEventType.TOOL_START,
        messageId: 'msg-1',
        tool_name: toolName,
      },
      input: '',
      sources: undefined,
      added: false,
      state,
      actions,
      recievedMessage: '',
      files: [],
    };
  }

  it('marks turn engaged on desktop_ TOOL_START', async () => {
    await toolLifecycleEvents(buildToolStartCtx('desktop_click_tool'));

    expect(useDesktopInspectorStore.getState().engagedChatId).toBe('chat-fg');
    expect(useDesktopInspectorStore.getState().isDesktopActive).toBe(true);
  });

  it('does not mark turn engaged on non-desktop TOOL_START', async () => {
    await toolLifecycleEvents(buildToolStartCtx('web_search_tool'));

    expect(useDesktopInspectorStore.getState().engagedChatId).toBeNull();
  });
});
