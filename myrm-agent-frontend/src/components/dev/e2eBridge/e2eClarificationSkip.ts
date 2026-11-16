/**
 * [INPUT]
 * - @/store/chat/clarificationCardAnswer::answerClarificationWithResume (POS: the join point every answer to a clarification card goes through)
 * - @/store/chat/clarificationState::findActivePendingClarification (POS: the card the conversation is still waiting on)
 * - @/store/useChatStore (POS: the message list and the send pipeline)
 *
 * [OUTPUT]
 * - skipActiveClarification: skip the card the conversation waits on the way its Skip button does
 *
 * [POS]
 * The skip of the CDP E2E bridge. It sends what a click on Skip sends, so a skip that reaches nobody fails the E2E
 * instead of passing around the product.
 */

import { answerClarificationWithResume } from '@/store/chat/clarificationCardAnswer';
import type { ClarificationDraft } from '@/store/chat/clarificationCardDraft';
import { findActivePendingClarification } from '@/store/chat/clarificationState';
import useChatStore from '@/store/useChatStore';

const EMPTY_DRAFT: ClarificationDraft = { input: '', selectedOptions: [], formTexts: {}, formSelections: {} };

/** `interruptId` is null for a card the server stored without one: its skip goes out unaddressed. */
export function skipActiveClarification(): { messageId: string; interruptId: string | null } {
  const { messages, sendMessage } = useChatStore.getState();
  const pending = findActivePendingClarification(messages);
  if (!pending) {
    throw new Error('e2e-no-active-clarification');
  }
  const { messageId, clarification } = pending;
  void answerClarificationWithResume(messageId, { value: {}, draft: EMPTY_DRAFT }, (resumeValue) =>
    sendMessage('', messageId, undefined, resumeValue),
  ).catch((error: unknown) => {
    console.error('[E2E_CLARIFICATION_SKIP] resume failed', error);
  });
  return { messageId, interruptId: clarification.interruptId ?? null };
}
