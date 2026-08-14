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

const browserViewUpdateData = {
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
};

describe('fileDiffEvents browser_view_update', () => {
  beforeEach(() => {
    useBrowserInspectorStore.getState().reset();
  });

  it('stores view data with sourceChatId, marks turn engaged, and does not open panel', async () => {
    useBrowserInspectorStore.setState({ isOpen: false });
    const { ctx } = buildCtx(browserViewUpdateData);

    await fileDiffEvents(ctx);

    const store = useBrowserInspectorStore.getState();
    expect(store.isBrowserActive).toBe(true);
    expect(store.engagedChatId).toBe('chat-bg');
    expect(store.isOpen).toBe(false);
    expect(store.viewData?.sourceChatId).toBe('chat-bg');
    expect(store.viewData?.pageUrl).toBe('https://example.com');
    // A turn-driven view must be flagged isTurnView=true so releaseTurnEngagement
    // can reclaim it on MESSAGE_END without force-closing a manually opened panel.
    expect(store.viewData?.isTurnView).toBe(true);
  });

  it('skips update when stream chatId is missing', async () => {
    const { ctx } = buildCtx(browserViewUpdateData);
    const firstMsg = ctx.state.messages[0];
    if (firstMsg) {
      firstMsg.chatId = '';
    }

    await fileDiffEvents(ctx);

    const store = useBrowserInspectorStore.getState();
    expect(store.viewData).toBeNull();
    expect(store.engagedChatId).toBeNull();
  });

  it('engages from state.chatId when the message list is empty (brand-new chat first turn)', async () => {
    useBrowserInspectorStore.setState({ isOpen: false });
    const { ctx } = buildCtx(browserViewUpdateData);
    ctx.state.messages = [];
    ctx.state.chatId = 'chat-bg';

    await fileDiffEvents(ctx);

    const store = useBrowserInspectorStore.getState();
    expect(store.isBrowserActive).toBe(true);
    expect(store.engagedChatId).toBe('chat-bg');
    expect(store.isOpen).toBe(false);
    expect(store.viewData?.sourceChatId).toBe('chat-bg');
  });
});
