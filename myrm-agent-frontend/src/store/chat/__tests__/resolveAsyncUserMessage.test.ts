import { describe, expect, it, beforeEach } from 'vitest';
import useChatStore from '@/store/useChatStore';
import type { Message } from '@/store/chat/types';

describe('useChatStore.resolveAsyncUserMessage', () => {
  beforeEach(() => {
    useChatStore.setState({
      chatId: 'chat-test-async',
      messages: [],
    });
  });

  it('updates status and resolvedText for matching messageId and callId', () => {
    const msg: Message = {
      messageId: 'msg-1',
      chatId: 'chat-test-async',
      createdAt: new Date(),
      content: 'Thinking...',
      role: 'assistant',
      asyncUserMessages: [
        {
          callId: 'call-101',
          message: 'Clarify deployment target?',
          category: 'question',
          recommendation: 'Use Kubernetes',
          status: 'pending',
          resolvedText: null,
        },
      ],
    };

    useChatStore.setState({ messages: [msg] });

    useChatStore.getState().resolveAsyncUserMessage('msg-1', 'call-101', 'Use Kubernetes');

    const updated = useChatStore.getState().messages[0];
    expect(updated.asyncUserMessages?.[0].status).toBe('resolved');
    expect(updated.asyncUserMessages?.[0].resolvedText).toBe('Use Kubernetes');
  });

  it('locates entry by callId even if messageId has slight variance', () => {
    const msg: Message = {
      messageId: 'msg-uuid-actual',
      chatId: 'chat-test-async',
      createdAt: new Date(),
      content: 'Running analysis...',
      role: 'assistant',
      asyncUserMessages: [
        {
          callId: 'call-202',
          message: 'Confirm migration step',
          category: 'question',
          status: 'pending',
          resolvedText: null,
        },
      ],
    };

    useChatStore.setState({ messages: [msg] });

    useChatStore.getState().resolveAsyncUserMessage('msg-stream-id-diff', 'call-202', 'Confirmed migration');

    const updated = useChatStore.getState().messages[0];
    expect(updated.asyncUserMessages?.[0].status).toBe('resolved');
    expect(updated.asyncUserMessages?.[0].resolvedText).toBe('Confirmed migration');
  });

  it('is a safe no-op when callId is not found', () => {
    const msg: Message = {
      messageId: 'msg-1',
      chatId: 'chat-test-async',
      createdAt: new Date(),
      content: 'Idle',
      role: 'assistant',
      asyncUserMessages: [
        {
          callId: 'call-303',
          message: 'Existing prompt',
          category: 'question',
          status: 'pending',
          resolvedText: null,
        },
      ],
    };

    useChatStore.setState({ messages: [msg] });

    useChatStore.getState().resolveAsyncUserMessage('msg-1', 'call-nonexistent', 'Anything');

    const updated = useChatStore.getState().messages[0];
    expect(updated.asyncUserMessages?.[0].status).toBe('pending');
    expect(updated.asyncUserMessages?.[0].resolvedText).toBeNull();
  });
});
