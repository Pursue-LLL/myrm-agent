import { beforeEach, describe, expect, it, vi } from 'vitest';

import { AgentEventType } from '@/store/chat/types';
import useChatStore from '@/store/useChatStore';
import useDesktopControlApprovalStore from '@/store/useDesktopControlApprovalStore';
import useDesktopInspectorStore from '@/store/useDesktopInspectorStore';
import type { StreamHandlerActions, StreamHandlerState } from '../../types';
import type { StreamCtx } from '../../streamContext';
import { fileDiffEvents } from '../fileDiffEvents';

function buildCtx(streamChatId = 'chat-fg'): StreamCtx {
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
    loading: true,
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
      type: AgentEventType.DESKTOP_CONTROL_APPROVAL_REQUEST,
      messageId: 'msg-1',
      data: {
        request_id: 'req-1',
        reason: 'Control app',
        operation: 'control',
        app_name: 'System Settings',
        window_title: 'Privacy',
        require_app_approval: true,
      },
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

describe('fileDiffEvents desktop_control_approval_request', () => {
  beforeEach(() => {
    useDesktopInspectorStore.getState().reset();
    useDesktopControlApprovalStore.getState().clear();
    useChatStore.setState({ chatId: undefined });
    vi.clearAllMocks();
  });

  it('opens inspector panel when stream chat matches foreground chat', async () => {
    useChatStore.setState({ chatId: 'chat-fg' });
    useDesktopInspectorStore.setState({ isOpen: false });

    await fileDiffEvents(buildCtx('chat-fg'));

    expect(useDesktopControlApprovalStore.getState().pending).toBe(true);
    expect(useDesktopControlApprovalStore.getState().requestId).toBe('req-1');
    expect(useDesktopInspectorStore.getState().isOpen).toBe(true);
  });

  it('does not open inspector panel when background stream chat differs from foreground chat', async () => {
    useChatStore.setState({ chatId: 'chat-fg' });
    useDesktopInspectorStore.setState({ isOpen: false });

    await fileDiffEvents(buildCtx('chat-bg'));

    expect(useDesktopControlApprovalStore.getState().pending).toBe(true);
    expect(useDesktopControlApprovalStore.getState().requestId).toBe('req-1');
    expect(useDesktopInspectorStore.getState().isOpen).toBe(false);
  });
});
