/**
 * [INPUT]
 * - @/store/chat/types::Message, MessageSpillover (POS: Chat message entity)
 * - ./messageUtils::stripUserMessageDisplayText (POS: Message text cleanup helpers)
 *
 * [OUTPUT]
 * - SPILLOVER_MIN_CHARS: length from which the server keeps a pasted text in a file instead of the conversation.
 * - normalizeSpillover: the persisted `spillover` metadata of a history message, or undefined.
 * - pastedTextOf: the collapsed form of a user message that is a very long paste, or null.
 * - userMessageDisplayText: the text a user message is listed by (titles, turn rail).
 *
 * [POS]
 * Pasted-text helpers shared by the composer notice, the user bubble and the places that list a message by its text.
 */
import type { Message, MessageSpillover } from '@/store/chat/types';
import { stripUserMessageDisplayText } from './messageUtils';

/** Mirrors the server's message size limit (`MESSAGE_MAX_CHARS`); longer pastes are kept in a file. */
export const SPILLOVER_MIN_CHARS = 16_000;

/** Mirrors the server's preview length (`PREVIEW_MAX_CHARS`). */
const SPILLOVER_PREVIEW_CHARS = 300;

export interface PastedText {
  chars: number;
  preview: string;
  /** Set while the text is still in memory (a message just sent); absent once only the file holds it. */
  fullText?: string;
}

/** Reads the server's `spillover` metadata (snake_case) into the shape the UI uses. */
export function normalizeSpillover(raw: unknown): MessageSpillover | undefined {
  if (typeof raw !== 'object' || raw === null) {
    return undefined;
  }
  const record = raw as Record<string, unknown>;
  const path = record.spillover_path;
  const chars = record.original_char_count;
  if (typeof path !== 'string' || !path || typeof chars !== 'number') {
    return undefined;
  }
  return { path, chars, preview: typeof record.preview === 'string' ? record.preview : '' };
}

/** A user message that is a very long paste reads as a character count plus its opening lines, not as the whole text. */
export function pastedTextOf(text: string, spillover?: MessageSpillover): PastedText | null {
  if (spillover) {
    return { chars: spillover.chars, preview: spillover.preview };
  }
  if (text.length > SPILLOVER_MIN_CHARS) {
    return { chars: text.length, preview: text.slice(0, SPILLOVER_PREVIEW_CHARS), fullText: text };
  }
  return null;
}

/** What a user message reads as in a title or list: a parked paste shows its opening lines, not its stored stub. */
export function userMessageDisplayText(message: Pick<Message, 'content' | 'spillover'>): string {
  return message.spillover?.preview || stripUserMessageDisplayText(message.content || '');
}
