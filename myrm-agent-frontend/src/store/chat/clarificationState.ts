/**
 * [OUTPUT]
 * - normalizeHydratedClarification: restore pending clarify fields (and the camelCase form) after DB hydrate
 * - findActivePendingClarification: locate the unanswered clarify card the conversation is still waiting on
 *
 * [POS]
 * Shared clarify state helpers for message hydrate and Composer takeover selection.
 */

import { normalizeClarificationForm } from './messageStream/streamHelpers';
import type { Message } from './types';

export function normalizeHydratedClarification(
  clarification: NonNullable<Message['clarification']>,
): NonNullable<Message['clarification']> {
  if (clarification.answered !== true) {
    clarification.answered = false;
  }
  // The server persists the raw snake_case form; read it exactly like the live event does.
  if (clarification.form) {
    clarification.form = normalizeClarificationForm(clarification.form);
  }
  return clarification;
}

/**
 * The card is waiting only until the user writes again: a newer user message replaces the question, so the composer,
 * the attention summary and the companion must not keep waiting for an answer nobody asks for any more.
 */
export function findActivePendingClarification(
  messages: Message[],
): { messageId: string; clarification: NonNullable<Message['clarification']> } | null {
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    const message = messages[index];
    if (message.role === 'user') {
      return null;
    }
    if (message.role === 'assistant' && message.clarification && !message.clarification.answered) {
      return { messageId: message.messageId, clarification: message.clarification };
    }
  }
  return null;
}
