/**
 * Tests for resolveStreamChatId: the stream chatId resolver used by handler
 * slices. Prefers the chatId captured at send time and falls back to the first
 * message's chatId, so a brand-new chat whose message list is still empty on the
 * first turn never resolves an empty chatId (which would silently no-op
 * inspector engagement/release).
 */
import { describe, expect, it } from 'vitest';

import { resolveStreamChatId } from '../handlerDeps';

const EMPTY_STATE = {
  messageAppeared: false,
  loading: false,
  scheduler: {} as never,
};

describe('resolveStreamChatId', () => {
  it('prefers state.chatId over messages[0].chatId', () => {
    expect(
      resolveStreamChatId({
        chatId: 'c1',
        messages: [{ chatId: 'old' } as never],
        ...EMPTY_STATE,
      } as never),
    ).toBe('c1');
  });

  it('falls back to messages[0].chatId when state.chatId is absent', () => {
    expect(
      resolveStreamChatId({
        messages: [{ chatId: 'c1' } as never],
        ...EMPTY_STATE,
      } as never),
    ).toBe('c1');
  });

  it('resolves the chatId for a brand-new chat first turn with an empty message list', () => {
    expect(
      resolveStreamChatId({
        chatId: 'new-chat',
        messages: [],
        ...EMPTY_STATE,
      } as never),
    ).toBe('new-chat');
  });

  it('trims surrounding whitespace', () => {
    expect(
      resolveStreamChatId({
        chatId: '  c1  ',
        messages: [],
        ...EMPTY_STATE,
      } as never),
    ).toBe('c1');
  });

  it('returns an empty string when neither source is available', () => {
    expect(
      resolveStreamChatId({
        messages: [],
        ...EMPTY_STATE,
      } as never),
    ).toBe('');
  });
});
