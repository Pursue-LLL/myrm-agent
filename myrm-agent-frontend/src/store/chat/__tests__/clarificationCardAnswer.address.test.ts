/**
 * An answer to a clarification card is addressed to the pause the card was announced for.
 *
 * Real scenario: the user presses skip. LangGraph reads an empty answer as a map of interrupt ids that names no pause,
 * so the answer reaches nobody and the agent never continues. The card remembers which pause it was announced for, and
 * the one join point every answer goes through sends the answer to that pause.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { answerClarificationWithResume } from '@/store/chat/clarificationCardAnswer';
import type { Message } from '@/store/chat/types';
import useChatStore from '@/store/useChatStore';

const MESSAGE_ID = 'msg-1';
const emptyDraft = { input: '', selectedOptions: [], formTexts: {}, formSelections: {} };

function openCard(interruptId?: string): void {
  const row: Message = {
    messageId: MESSAGE_ID,
    chatId: 'chat-1',
    createdAt: new Date(),
    content: '',
    role: 'assistant',
    clarification: { answered: false, ...(interruptId && { interruptId }) },
  };
  useChatStore.setState({ chatId: 'chat-1', messages: [row] });
}

const answerRecord = () => useChatStore.getState().messages[0]?.clarification?.answerRecord;

describe('answerClarificationWithResume addressing', () => {
  const sendResume = vi.fn<(resumeValue: unknown) => Promise<unknown>>();

  beforeEach(() => {
    sendResume.mockReset();
    sendResume.mockResolvedValue(undefined);
  });

  it('sends an answer to the pause the card was announced for', async () => {
    openCard('int-1');

    await answerClarificationWithResume(MESSAGE_ID, { value: { strategy: 'canary' }, draft: emptyDraft }, sendResume);

    expect(sendResume).toHaveBeenCalledExactlyOnceWith({ strategy: 'canary', interruptId: 'int-1' });
  });

  it('addresses a skip, whose answer is empty', async () => {
    openCard('int-1');

    await answerClarificationWithResume(MESSAGE_ID, { value: {}, draft: emptyDraft }, sendResume);

    expect(sendResume).toHaveBeenCalledExactlyOnceWith({ interruptId: 'int-1' });
  });

  it('keeps the address out of the record the settled card shows', async () => {
    openCard('int-1');

    await answerClarificationWithResume(MESSAGE_ID, { value: { strategy: 'canary' }, draft: emptyDraft }, sendResume);

    expect(answerRecord()).toEqual({ by: 'user', value: { strategy: 'canary' } });
  });

  it('does not write the address into the answer the caller holds', async () => {
    openCard('int-1');
    const value = { strategy: 'canary' };

    await answerClarificationWithResume(MESSAGE_ID, { value, draft: emptyDraft }, sendResume);

    expect(value).toEqual({ strategy: 'canary' });
  });

  it('sends the bare answer for a card announced without an id', async () => {
    openCard();

    await answerClarificationWithResume(MESSAGE_ID, { value: { strategy: 'canary' }, draft: emptyDraft }, sendResume);
    openCard();
    await answerClarificationWithResume(MESSAGE_ID, { value: {}, draft: emptyDraft }, sendResume);

    expect(sendResume.mock.calls).toEqual([[{ strategy: 'canary' }], [{}]]);
  });
});
