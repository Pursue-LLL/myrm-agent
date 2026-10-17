/**
 * Tests for isStreamForOpenChat: the gate that keeps a chat running in the background from writing the single-slot
 * stores (subagent tree, inspector panels), which describe only the chat the user has open.
 *
 * Real scenario: chat A is still streaming while the user works in chat B, or has pressed "new chat" and has no chat
 * id yet. A's events must not be taken for the open chat's.
 */
import { beforeEach, describe, expect, it } from 'vitest';

import useChatStore from '@/store/useChatStore';
import { isStreamForOpenChat } from '../handlerDeps';

const EMPTY_STATE = {
  messageAppeared: false,
  loading: false,
  scheduler: {} as never,
};

const streamOf = (chatId: string | undefined, firstMessageChatId?: string) =>
  ({
    chatId,
    messages: firstMessageChatId ? [{ chatId: firstMessageChatId }] : [],
    ...EMPTY_STATE,
  }) as never;

describe('isStreamForOpenChat', () => {
  beforeEach(() => {
    useChatStore.setState({ chatId: 'chat-open' });
  });

  it('accepts the stream of the chat that is open', () => {
    expect(isStreamForOpenChat(streamOf('chat-open'))).toBe(true);
  });

  it('refuses the stream of another chat that is still running in the background', () => {
    expect(isStreamForOpenChat(streamOf('chat-background'))).toBe(false);
  });

  it('refuses every stream while no chat is open, as after pressing "new chat"', () => {
    useChatStore.setState({ chatId: undefined });
    expect(isStreamForOpenChat(streamOf('chat-background'))).toBe(false);

    useChatStore.setState({ chatId: '' });
    expect(isStreamForOpenChat(streamOf('chat-background'))).toBe(false);
  });

  it('refuses a stream that cannot name its chat, even while no chat is open', () => {
    expect(isStreamForOpenChat(streamOf(undefined))).toBe(false);

    useChatStore.setState({ chatId: undefined });
    expect(isStreamForOpenChat(streamOf(undefined))).toBe(false);
  });

  it('resolves the stream chat from the first message when the send-time chat is missing', () => {
    expect(isStreamForOpenChat(streamOf(undefined, 'chat-open'))).toBe(true);
    expect(isStreamForOpenChat(streamOf(undefined, 'chat-background'))).toBe(false);
  });

  it('ignores whitespace around either id', () => {
    useChatStore.setState({ chatId: '  chat-open ' });
    expect(isStreamForOpenChat(streamOf(' chat-open  '))).toBe(true);
  });
});
