/**
 * [INPUT]
 * - @/store/chat/types::Message (POS: chat message shape; `isSystemNotice` marks rows the server appended on its own)
 * - ./wakeupNotice::isInertWakeupNotice (POS: notes of settled background tasks that started no turn)
 *
 * [OUTPUT]
 * - findLastTurnAnswerId: id of the assistant message that answers the latest user turn, or null.
 *
 * [POS]
 * Regenerate acts on the latest turn only (the server replaces the answer of the last user message), so only that
 * turn's answer may offer it. A system notice is not an answer: it never carries the action and never hides the
 * answer it follows. A note of a settled background task that started no turn is not a turn either, so it never
 * hides the answer before it (the server skips it the same way).
 */

import type { Message } from '@/store/chat/types';
import { isInertWakeupNotice } from './wakeupNotice';

export function findLastTurnAnswerId(messages: readonly Message[]): string | null {
  for (let i = messages.length - 1; i >= 0; i--) {
    const message = messages[i];
    if (message.role === 'user') {
      if (isInertWakeupNotice(message.wakeupNotice)) {
        continue;
      }
      return null;
    }
    if (message.role === 'assistant' && !message.isSystemNotice) {
      return message.messageId;
    }
  }
  return null;
}
