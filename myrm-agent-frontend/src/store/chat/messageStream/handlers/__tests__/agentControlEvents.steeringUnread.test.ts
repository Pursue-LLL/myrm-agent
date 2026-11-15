/**
 * A turn that ended by itself without reading the instructions it accepted hands them back in `steering_unread`:
 * they rejoin the chat's follow-up queue (the real queue store), which sends them like any other queued message.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';

const { mockShowToast, mockIsStreamForOpenChat } = vi.hoisted(() => ({
  mockShowToast: vi.fn(),
  mockIsStreamForOpenChat: vi.fn(() => true),
}));

vi.mock('@/services/i18nToastService', () => ({
  showI18nToast: mockShowToast,
  translateI18nKey: (_key: string, fallback?: string) => fallback ?? _key,
}));

vi.mock('../handlerDeps', async () => {
  const { useMessageQueueStore } = await import('@/store/chat/useMessageQueueStore');
  return {
    AgentEventType: { STEERING_UNREAD: 'steering_unread' },
    isStreamForOpenChat: mockIsStreamForOpenChat,
    resolveStreamChatId: (state: { chatId?: string }) => state.chatId ?? '',
    useMessageQueueStore,
  };
});

import { useMessageQueueStore } from '@/store/chat/useMessageQueueStore';
import { agentControlEvents } from '../agentControlEvents';
import type { StreamCtx } from '../../streamContext';

const CHAT = 'chat-1';

function steeringUnread(messages: string[], chatId: string = CHAT): StreamCtx {
  return {
    data: { type: 'steering_unread', messageId: 'msg-1', data: { count: messages.length, messages } } as never,
    input: '',
    sources: undefined,
    added: false,
    recievedMessage: 'answer so far',
    state: { chatId, messages: [] } as never,
    actions: {} as never,
    files: [],
  };
}

const queuedTexts = (chatId: string = CHAT): string[] =>
  (useMessageQueueStore.getState().queues[chatId]?.items ?? []).map((item) => item.text);

describe('agentControlEvents steering_unread', () => {
  beforeEach(() => {
    useMessageQueueStore.setState({ queues: {} });
    mockShowToast.mockClear();
    mockIsStreamForOpenChat.mockReturnValue(true);
  });

  it('puts every returned instruction in the stream chat queue, in the order it was accepted', async () => {
    await agentControlEvents(steeringUnread(['use the 2026 rows', 'and cite the source']));

    expect(queuedTexts()).toEqual(['use the 2026 rows', 'and cite the source']);
  });

  it('queues them behind the messages already waiting', async () => {
    useMessageQueueStore.getState().enqueue(CHAT, { text: 'already waiting', files: [] });

    await agentControlEvents(steeringUnread(['returned']));

    expect(queuedTexts()).toEqual(['already waiting', 'returned']);
  });

  it('leaves the queue open so the drain sends them once the chat is idle', async () => {
    await agentControlEvents(steeringUnread(['returned']));

    expect(useMessageQueueStore.getState().queues[CHAT]?.pausedReason).toBeNull();
  });

  it('keeps the turn state the stream has built so far', async () => {
    const turn = await agentControlEvents(steeringUnread(['returned']));

    expect(turn).toEqual({ added: false, recievedMessage: 'answer so far', meta: undefined });
  });

  it('tells the user in the open chat where the instructions went', async () => {
    await agentControlEvents(steeringUnread(['returned']));

    expect(mockShowToast).toHaveBeenCalledWith('chat.queue.steeringReturned', undefined, { type: 'info' });
  });

  it('queues for a chat in the background without a toast about another conversation', async () => {
    mockIsStreamForOpenChat.mockReturnValue(false);

    await agentControlEvents(steeringUnread(['returned'], 'chat-2'));

    expect(queuedTexts('chat-2')).toEqual(['returned']);
    expect(queuedTexts()).toEqual([]);
    expect(mockShowToast).not.toHaveBeenCalled();
  });
});
