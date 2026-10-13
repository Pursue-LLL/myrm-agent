/**
 * [INPUT]
 * - @/store/chat/types::Message (POS: chat message shape; `isSystemNotice` marks rows the server appended on its own)
 *
 * [OUTPUT]
 * - findLastTurnAnswerId: id of the assistant message that answers the latest user turn, or null.
 *
 * [POS]
 * Retry and undo act on the latest turn only (the server replaces / deletes everything from the last user message
 * on), so only that turn's answer may offer them. A system notice is not an answer: it never carries the actions and
 * never hides the answer it follows.
 */

import type { Message } from '@/store/chat/types';

export function findLastTurnAnswerId(messages: readonly Message[]): string | null {
  for (let i = messages.length - 1; i >= 0; i--) {
    const message = messages[i];
    if (message.role === 'user') {
      return null;
    }
    if (message.role === 'assistant' && !message.isSystemNotice) {
      return message.messageId;
    }
  }
  return null;
}
