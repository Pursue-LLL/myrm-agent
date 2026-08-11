import { beforeEach, describe, expect, it, vi } from 'vitest';

import { AgentEventType } from '@/store/chat/types';
import useBrowserInspectorStore from '@/store/useBrowserInspectorStore';
import useChatStore from '@/store/useChatStore';
import type { StreamHandlerActions, StreamHandlerState } from '../../types';
import type { StreamCtx } from '../../streamContext';
import { toolLifecycleEvents } from '../toolLifecycleEvents';

function buildCtx(toolName: string, streamChatId = 'chat-fg'): StreamCtx {
  const state: StreamHandlerState = {
    messages: [
      {
        messageId: 'msg-1',
        chatId: streamChatId,
        createdAt: new Date(),
        role: 'assistant',
        content: '',
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

describe('toolLifecycleEvents browser inspector', () => {
  beforeEach(() => {
    useBrowserInspectorStore.getState().reset();
    useChatStore.setState({ chatId: undefined });
  });

  it('opens panel on browser TOOL_START when stream chat matches foreground chat', async () => {
    useChatStore.setState({ chatId: 'chat-fg' });
    await toolLifecycleEvents(buildCtx('browser_snapshot_tool'));

    const store = useBrowserInspectorStore.getState();
    expect(store.isBrowserActive).toBe(true);
    expect(store.isOpen).toBe(true);
  });

  it('does not open panel when background stream chat differs from foreground chat', async () => {
    useChatStore.setState({ chatId: 'chat-fg' });
    await toolLifecycleEvents(buildCtx('browser_navigate_tool', 'chat-bg'));

    const store = useBrowserInspectorStore.getState();
    expect(store.isBrowserActive).toBe(true);
    expect(store.isOpen).toBe(false);
  });
});
