/**
 * [INPUT]
 * - @/store/useChatStore (POS: HITL cards live on assistant rows of the message list)
 * - ./streamErrors::ApprovalExpiredError (POS: the timeout already settled the card, so the answer is not undone)
 *
 * [OUTPUT]
 * - HitlCardKind: card fields that carry an `answered` flag and take over the composer while pending
 * - setHitlCardAnswered: flip the answered flag of a card on its assistant row
 * - answerHitlCardWithResume: close the card, send the resumed answer, reopen the card if the server never took it
 *
 * [POS]
 * Shared answer flow of the clarification and directory cards. A resume request streams the whole resumed run, and the
 * composer stays taken over until the card's row says answered, so the card closes before the request instead of after.
 */

import useChatStore from '@/store/useChatStore';

import { ApprovalExpiredError } from './streamErrors';

export type HitlCardKind = 'clarification' | 'directoryRequest';

const findCard = (kind: HitlCardKind, messageId: string) =>
  useChatStore.getState().messages.find((m) => m.messageId === messageId && m.role === 'assistant')?.[kind];

export function setHitlCardAnswered(kind: HitlCardKind, messageId: string, answered: boolean): void {
  useChatStore.setState((state) => {
    const card = state.messages.find((m) => m.messageId === messageId && m.role === 'assistant')?.[kind];
    if (card) {
      card.answered = answered;
    }
  });
}

/**
 * Rethrows whatever `sendResume` throws so the caller reports it. The card stays closed when the timeout already
 * settled it, and when the resumed run has replaced or settled it since: only the exact card closed here is reopened.
 */
export async function answerHitlCardWithResume(
  kind: HitlCardKind,
  messageId: string,
  sendResume: () => Promise<unknown>,
): Promise<void> {
  setHitlCardAnswered(kind, messageId, true);
  const closedCard = findCard(kind, messageId);
  try {
    await sendResume();
  } catch (error) {
    if (!(error instanceof ApprovalExpiredError) && closedCard && findCard(kind, messageId) === closedCard) {
      setHitlCardAnswered(kind, messageId, false);
    }
    throw error;
  }
}
