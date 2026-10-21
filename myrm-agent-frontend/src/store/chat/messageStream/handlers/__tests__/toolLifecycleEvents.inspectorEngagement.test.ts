/**
 * Tests that toolLifecycleEvents resolves the stream chatId for a brand-new chat's
 * first turn (empty message list) when engaging the browser/desktop inspectors.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { AgentEventType } from '@/store/chat/types';
import useBrowserInspectorStore from '@/store/useBrowserInspectorStore';
import useDesktopInspectorStore from '@/store/useDesktopInspectorStore';
import type { StreamHandlerActions, StreamHandlerState } from '../../types';
import type { StreamCtx } from '../../streamContext';
import { toolLifecycleEvents } from '../toolLifecycleEvents';

const mockChatId = { value: 'chat-bg' };

vi.mock('@/store/useChatStore', () => ({
  default: { getState: () => ({ chatId: mockChatId.value }) },
}));

vi.mock('@/lib/api', () => ({
  apiRequest: vi.fn(async () => ({
    screenshot_base64: 'shot',
    mime_type: 'image/png',
    refs: {},
    app_name: 'Calculator',
    window_title: '',
    scope: 'app',
    needs_permission: false,
    viewport_width: 100,
    viewport_height: 100,
  })),
}));

function buildCtx(data: StreamCtx['data']): { ctx: StreamCtx } {
  const state: StreamHandlerState = {
    messages: [],
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

describe('toolLifecycleEvents inspector engagement', () => {
  beforeEach(() => {
    useBrowserInspectorStore.getState().reset();
    useDesktopInspectorStore.getState().reset();
    mockChatId.value = 'chat-bg';
  });

  it('engages and opens the browser panel for a brand-new chat first turn', async () => {
    const { ctx } = buildCtx({
      type: AgentEventType.TOOL_START,
      tool_name: 'browser_navigate',
      messageId: 'msg-1',
    });
    ctx.state.chatId = 'chat-bg';

    await toolLifecycleEvents(ctx);

    const store = useBrowserInspectorStore.getState();
    expect(store.isBrowserActive).toBe(true);
    expect(store.engagedChatId).toBe('chat-bg');
    expect(store.isOpen).toBe(true);
  });

  it('engages but keeps the panel closed when the turn belongs to a background pane', async () => {
    useBrowserInspectorStore.setState({ isOpen: false });
    mockChatId.value = 'active-pane';
    const { ctx } = buildCtx({
      type: AgentEventType.TOOL_START,
      tool_name: 'browser_navigate',
      messageId: 'msg-1',
    });
    ctx.state.chatId = 'chat-bg';

    await toolLifecycleEvents(ctx);

    const store = useBrowserInspectorStore.getState();
    expect(store.engagedChatId).toBe('chat-bg');
    expect(store.isBrowserActive).toBe(true);
    expect(store.isOpen).toBe(false);
  });

  it('refreshes the desktop snapshot from state.chatId for a brand-new chat first turn', async () => {
    const { ctx } = buildCtx({
      type: AgentEventType.TOOL_END,
      tool_name: 'desktop_click',
      messageId: 'msg-1',
      duration_ms: 100,
    });
    ctx.state.messages = [{ messageId: 'msg-1', chatId: '', createdAt: new Date(), role: 'assistant', content: '' }];
    ctx.state.chatId = 'chat-bg';

    await toolLifecycleEvents(ctx);
    await vi.dynamicImportSettled();
    await new Promise((resolve) => setTimeout(resolve, 0));

    const store = useDesktopInspectorStore.getState();
    expect(store.isDesktopActive).toBe(true);
    expect(store.viewData?.sourceChatId).toBe('chat-bg');
  });
});
