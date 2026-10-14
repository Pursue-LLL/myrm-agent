import { beforeEach, describe, expect, it } from 'vitest';

import type { Message } from '@/store/chat/types';
import useChatStore from '@/store/useChatStore';
import { readLastMessage } from '../lastMessage';
import type { StreamHandlerActions } from '../types';

const CHAT_ID = 'chat-last-message';

const liveSetMessages: StreamHandlerActions['setMessages'] = (updater) =>
  useChatStore.setState((draft) => updater(draft));

function message(messageId: string, role: Message['role'], content: string): Message {
  return { messageId, chatId: CHAT_ID, role, content, createdAt: new Date() };
}

describe('readLastMessage', () => {
  beforeEach(() => {
    useChatStore.setState({ chatId: CHAT_ID, messages: [] });
  });

  it('finds the message written after the stream opened, which its start-of-turn snapshot does not hold', () => {
    useChatStore.setState({ messages: [message('user-1', 'user', 'question')] });
    const snapshot = useChatStore.getState().messages;
    useChatStore.setState((draft) => {
      draft.messages.push(message('assistant-1', 'assistant', 'answer'));
    });

    expect(snapshot[snapshot.length - 1].messageId).toBe('user-1');
    expect(readLastMessage(liveSetMessages)?.messageId).toBe('assistant-1');
  });

  it('returns a copy that neither follows later writes nor dies with the draft it was read from', () => {
    useChatStore.setState({ messages: [message('assistant-1', 'assistant', 'answer')] });

    const copy = readLastMessage(liveSetMessages);
    useChatStore.setState((draft) => {
      draft.messages[0].content = 'rewritten';
    });

    expect(copy).toMatchObject({ messageId: 'assistant-1', content: 'answer' });
  });

  it('returns nothing for a chat without messages', () => {
    expect(readLastMessage(liveSetMessages)).toBeUndefined();
  });

  it('also reads plain state that is not an immer draft', () => {
    const last = message('assistant-1', 'assistant', 'answer');

    const read = readLastMessage((updater) => updater({ messages: [last], loading: false, messageAppeared: false }));

    expect(read).toBe(last);
  });
});
