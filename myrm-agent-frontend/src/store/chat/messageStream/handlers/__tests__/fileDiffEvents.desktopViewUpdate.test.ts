import { beforeEach, describe, expect, it, vi } from 'vitest';

import { AgentEventType } from '@/store/chat/types';
import useDesktopInspectorStore from '@/store/useDesktopInspectorStore';
import type { StreamHandlerActions, StreamHandlerState } from '../../types';
import type { StreamCtx } from '../../streamContext';
import { fileDiffEvents } from '../fileDiffEvents';

function buildCtx(data: StreamCtx['data'], chatId = 'chat-desk'): { ctx: StreamCtx } {
  const state: StreamHandlerState = {
    messages: [
      {
        messageId: 'msg-1',
        chatId,
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
    ctx: {
      data,
      input: '',
      sources: undefined,
      added: false,
      state,
      actions,
      recievedMessage: '',
      files: [],
    },
  };
}

describe('fileDiffEvents desktop_view_update', () => {
  beforeEach(() => {
    useDesktopInspectorStore.getState().reset();
  });

  it('stores view data with sourceChatId', async () => {
    useDesktopInspectorStore.setState({ isOpen: false });
    const { ctx } = buildCtx({
      type: AgentEventType.DESKTOP_VIEW_UPDATE,
      messageId: 'msg-1',
      data: {
        screenshot_base64: 'abc',
        mime_type: 'image/jpeg',
        refs: {},
        app_name: 'TextEdit',
        window_title: 'Untitled',
        scope: 'app',
        needs_permission: false,
        viewport_width: 1280,
        viewport_height: 720,
      },
    });

    await fileDiffEvents(ctx);

    const store = useDesktopInspectorStore.getState();
    expect(store.isDesktopActive).toBe(true);
    expect(store.isOpen).toBe(false);
    expect(store.viewData?.sourceChatId).toBe('chat-desk');
    expect(store.viewData?.appName).toBe('TextEdit');
  });

  it('skips update when stream chatId is missing', async () => {
    const { ctx } = buildCtx({
      type: AgentEventType.DESKTOP_VIEW_UPDATE,
      messageId: 'msg-1',
      data: {
        screenshot_base64: 'abc',
        mime_type: 'image/jpeg',
        refs: {},
        app_name: 'TextEdit',
        window_title: 'Untitled',
        scope: 'app',
        needs_permission: false,
        viewport_width: 1280,
        viewport_height: 720,
      },
    });
    ctx.state.messages[0]!.chatId = '';

    await fileDiffEvents(ctx);

    expect(useDesktopInspectorStore.getState().viewData).toBeNull();
  });

  it('engages from state.chatId when the message list is empty (brand-new chat first turn)', async () => {
    useDesktopInspectorStore.setState({ isOpen: false });
    const { ctx } = buildCtx({
      type: AgentEventType.DESKTOP_VIEW_UPDATE,
      messageId: 'msg-1',
      data: {
        screenshot_base64: 'abc',
        mime_type: 'image/jpeg',
        refs: {},
        app_name: 'TextEdit',
        window_title: 'Untitled',
        scope: 'app',
        needs_permission: false,
        viewport_width: 1280,
        viewport_height: 720,
      },
    });
    ctx.state.messages = [];
    ctx.state.chatId = 'chat-desk';

    await fileDiffEvents(ctx);

    const store = useDesktopInspectorStore.getState();
    expect(store.isDesktopActive).toBe(true);
    expect(store.isOpen).toBe(false);
    expect(store.viewData?.sourceChatId).toBe('chat-desk');
  });
});
