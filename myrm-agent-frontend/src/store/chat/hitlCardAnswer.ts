/**
 * [INPUT]
 * - @/store/useChatStore (POS: HITL cards live on assistant rows of the message list)
 * - ./streamErrors::ApprovalExpiredError (POS: the timeout already settled the card, so the answer is not undone)
 * - ./hitlCardDraft (POS: the user's unsent input, kept while the card is closed)
 *
 * [OUTPUT]
 * - settleHitlCard: mark a card answered and keep how it was answered
 * - answerHitlCardWithResume: close the card, send the resumed answer, reopen the card if the server never took it
 *
 * [POS]
 * Shared answer flow of the clarification and directory cards. A resume request streams the whole resumed run, and the
 * composer stays taken over until the card's row says answered, so the card closes as soon as the request is sent.
 */

import useChatStore from '@/store/useChatStore';

import { clearHitlCardDraft, saveHitlCardDraft, type HitlCardDrafts, type HitlCardKind } from './hitlCardDraft';
import { ApprovalExpiredError } from './streamErrors';
import type { HitlAnswerRecord, Message } from './types';

type HitlCard = NonNullable<Message[HitlCardKind]>;

const cardRow = (messages: Message[], messageId: string) =>
  messages.find((m) => m.messageId === messageId && m.role === 'assistant');

const findCard = (kind: HitlCardKind, messageId: string) =>
  cardRow(useChatStore.getState().messages, messageId)?.[kind];

// The value the server resumes with when its timeout settles the card, and persists in the same record.
const timeoutRecord = (kind: HitlCardKind): HitlAnswerRecord => ({
  by: 'timeout',
  value: kind === 'clarification' ? {} : { granted: false },
});

function updateCard(kind: HitlCardKind, messageId: string, apply: (card: HitlCard) => void): void {
  useChatStore.setState((state) => {
    const card = cardRow(state.messages, messageId)?.[kind];
    if (card) {
      apply(card);
    }
  });
}

export function settleHitlCard(kind: HitlCardKind, messageId: string, record: HitlAnswerRecord): void {
  updateCard(kind, messageId, (card) => {
    card.answered = true;
    card.answerRecord = record;
  });
}

function reopenHitlCard(kind: HitlCardKind, messageId: string): void {
  updateCard(kind, messageId, (card) => {
    card.answered = false;
    delete card.answerRecord;
  });
}

/**
 * Rethrows whatever `sendResume` throws so the caller reports it. When the timeout already settled the card, the card
 * stays closed and shows the timeout instead of the answer that came too late. A card the resumed run has replaced or
 * settled since is left alone: only the exact card closed here is reopened or rewritten. `draft` is what the user wrote;
 * it is restored if the card comes back and dropped once the answer is settled either way.
 */
export async function answerHitlCardWithResume<K extends HitlCardKind>(
  kind: K,
  messageId: string,
  answer: { value: unknown; draft: HitlCardDrafts[K] },
  sendResume: () => Promise<unknown>,
): Promise<void> {
  saveHitlCardDraft(kind, messageId, answer.draft);
  settleHitlCard(kind, messageId, { by: 'user', value: answer.value });
  const closedCard = findCard(kind, messageId);
  const isStillClosedCard = () => closedCard !== undefined && findCard(kind, messageId) === closedCard;
  try {
    await sendResume();
    clearHitlCardDraft(kind, messageId);
  } catch (error) {
    if (error instanceof ApprovalExpiredError) {
      clearHitlCardDraft(kind, messageId);
      if (isStillClosedCard()) {
        settleHitlCard(kind, messageId, timeoutRecord(kind));
      }
    } else if (isStillClosedCard()) {
      reopenHitlCard(kind, messageId);
    }
    throw error;
  }
}
