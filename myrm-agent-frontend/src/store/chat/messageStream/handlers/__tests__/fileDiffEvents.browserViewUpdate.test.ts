import { beforeEach, describe, expect, it, vi } from 'vitest';

import { AgentEventType } from '@/store/chat/types';
import useBrowserInspectorStore from '@/store/useBrowserInspectorStore';
import type { StreamHandlerActions, StreamHandlerState } from '../../types';
import type { StreamCtx } from '../../streamContext';
import { fileDiffEvents } from '../fileDiffEvents';

function buildCtx(data: StreamCtx['data'], chatId = 'chat-bg'): { ctx: StreamCtx } {
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

describe('fileDiffEvents browser_view_update', () => {
  beforeEach(() => {
    useBrowserInspectorStore.getState().reset();
  });

  it('stores view data with sourceChatId and does not open panel', async () => {
    useBrowserInspectorStore.setState({ isOpen: false });
    const { ctx } = buildCtx({
      type: AgentEventType.BROWSER_VIEW_UPDATE,
      messageId: 'msg-1',
      data: {
        screenshot_base64: 'abc',
        mime_type: 'image/jpeg',
        refs: {
          e1: {
            role: 'button',
            name: 'Go',
            nth: null,
            bbox: {
              x: 0,
              y: 0,
              width: 1,
              height: 1,
              centerX: 0.5,
              centerY: 0.5,
              viewport_x: 0,
              viewport_y: 0,
              viewport_width: 1280,
              viewport_height: 720,
            },
            position: null,
          },
        },
        page_url: 'https://example.com',
        page_title: 'Example',
        viewport_width: 1280,
        viewport_height: 720,
      },
    });

    await fileDiffEvents(ctx);

    const store = useBrowserInspectorStore.getState();
    expect(store.isBrowserActive).toBe(true);
    expect(store.isOpen).toBe(false);
    expect(store.viewData?.sourceChatId).toBe('chat-bg');
    expect(store.viewData?.pageUrl).toBe('https://example.com');
  });

  it('skips update when stream chatId is missing', async () => {
    const { ctx } = buildCtx({
      type: AgentEventType.BROWSER_VIEW_UPDATE,
      messageId: 'msg-1',
      data: {
        screenshot_base64: 'abc',
        mime_type: 'image/jpeg',
        refs: {},
        page_url: 'https://example.com',
        page_title: 'Example',
        viewport_width: 1280,
        viewport_height: 720,
      },
    });
    ctx.state.messages[0]!.chatId = '';

    await fileDiffEvents(ctx);

    expect(useBrowserInspectorStore.getState().viewData).toBeNull();
  });
});
