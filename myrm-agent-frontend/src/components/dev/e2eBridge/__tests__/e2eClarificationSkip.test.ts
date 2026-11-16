/**
 * The E2E bridge skips a clarification card the way its Skip button does.
 *
 * Real scenario: the bridge once sent an empty answer of its own. That answer names no pause, so the agent never
 * continued while the E2E that used the bridge still passed. The bridge now goes through the answer flow, which
 * addresses the skip to the pause the card was announced for.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { skipActiveClarification } from '@/components/dev/e2eBridge/e2eClarificationSkip';
import type { Message } from '@/store/chat/types';
import useChatStore from '@/store/useChatStore';

const CARD_ID = 'msg-card';
const sendMessage = vi.fn<(...args: unknown[]) => Promise<void>>();

const row = (messageId: string, role: Message['role'], clarification?: Message['clarification']): Message => ({
  messageId,
  chatId: 'chat-1',
  createdAt: new Date(),
  content: role === 'user' ? 'ask me' : '',
  role,
  ...(clarification && { clarification }),
});

function conversation(...rows: Message[]): void {
  useChatStore.setState({ chatId: 'chat-1', messages: rows, sendMessage: sendMessage as never });
}

describe('skipActiveClarification', () => {
  beforeEach(() => {
    sendMessage.mockReset();
    sendMessage.mockResolvedValue(undefined);
  });

  it('sends the skip addressed to the pause the card was announced for and closes the card', () => {
    conversation(row('msg-user', 'user'), row(CARD_ID, 'assistant', { answered: false, interruptId: 'int-1' }));

    const started = skipActiveClarification();

    expect(started).toEqual({ messageId: CARD_ID, interruptId: 'int-1' });
    expect(sendMessage).toHaveBeenCalledExactlyOnceWith('', CARD_ID, undefined, { interruptId: 'int-1' });
    expect(useChatStore.getState().messages[1]?.clarification).toMatchObject({
      answered: true,
      answerRecord: { by: 'user', value: {} },
    });
  });

  it('reports a card the server stored without an id and sends its skip unaddressed', () => {
    conversation(row('msg-user', 'user'), row(CARD_ID, 'assistant', { answered: false }));

    expect(skipActiveClarification()).toEqual({ messageId: CARD_ID, interruptId: null });
    expect(sendMessage).toHaveBeenCalledExactlyOnceWith('', CARD_ID, undefined, {});
  });

  it('refuses to skip a card the conversation has moved past', () => {
    conversation(row(CARD_ID, 'assistant', { answered: false, interruptId: 'int-1' }), row('msg-user', 'user'));

    expect(() => skipActiveClarification()).toThrow('e2e-no-active-clarification');
    expect(sendMessage).not.toHaveBeenCalled();
  });
});
