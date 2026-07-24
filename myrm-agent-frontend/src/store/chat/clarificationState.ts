/**
 * [OUTPUT]
 * - normalizeHydratedClarification: restore pending clarify fields after DB hydrate
 * - findActivePendingClarification: locate the latest unanswered assistant clarify turn
 *
 * [POS]
 * Shared clarify state helpers for message hydrate and Composer takeover selection.
 */

import type { Message } from './types';

export function normalizeHydratedClarification(
  clarification: NonNullable<Message['clarification']>,
): NonNullable<Message['clarification']> {
  if (clarification.answered !== true) {
    clarification.answered = false;
  }
  if (clarification.isResumeMode === undefined) {
    const source = (clarification as { source?: string }).source;
    clarification.isResumeMode = source !== 'deep_research';
  }
  return clarification;
}

export function findActivePendingClarification(
  messages: Message[],
): { messageId: string; clarification: NonNullable<Message['clarification']> } | null {
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    const message = messages[index];
    if (message.role !== 'assistant') {
      continue;
    }
    if (message.clarification && !message.clarification.answered) {
      return { messageId: message.messageId, clarification: message.clarification };
    }
    continue;
  }
  return null;
}
