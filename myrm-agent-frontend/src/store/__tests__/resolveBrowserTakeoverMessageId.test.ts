import { beforeEach, describe, expect, it } from 'vitest';

import useApprovalStore, { resolveBrowserTakeoverMessageId } from '@/store/useApprovalStore';
import useBrowserTakeoverStore from '@/store/useBrowserTakeoverStore';
import useChatStore from '@/store/useChatStore';

describe('resolveBrowserTakeoverMessageId', () => {
  beforeEach(() => {
    useBrowserTakeoverStore.getState().completeTakeover();
    useApprovalStore.getState().clearQueue();
    useChatStore.setState({
      messages: [],
      currentSessionMessageId: null,
      chatId: 'chat-1',
    });
  });

  it('returns trimmed fallback when store snapshot has messageId', () => {
    expect(resolveBrowserTakeoverMessageId(' msg-42 ')).toBe('msg-42');
  });

  it('falls back to last assistant messageId when store snapshot is empty', () => {
    useChatStore.setState({
      messages: [
        {
          role: 'assistant',
          messageId: 'assistant-msg-9',
          content: '',
          chatId: 'chat-1',
          createdAt: new Date(),
        },
      ],
    });

    expect(resolveBrowserTakeoverMessageId('')).toBe('assistant-msg-9');
  });

  it('falls back to pending browser_takeover approval payload messageId', () => {
    useApprovalStore.getState().openApproval({
      approval_id: 'appr-takeover-1',
      user_id: 'user-1',
      action_type: 'browser_takeover',
      status: 'PENDING',
      severity: 'warning',
      chat_id: 'chat-1',
      payload: {
        messageId: 'payload-msg-7',
        reason: 'Enter SMS code',
      },
    });
    useBrowserTakeoverStore.getState().completeTakeover();

    expect(resolveBrowserTakeoverMessageId(undefined)).toBe('payload-msg-7');
  });
});
