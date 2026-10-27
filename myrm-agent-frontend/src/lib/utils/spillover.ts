/**
 * [INPUT]
 * - @/store/chat/types::Message, MessageSpillover (POS: Chat message entity)
 * - ./messageUtils::stripUserMessageDisplayText (POS: Message text cleanup helpers)
 *
 * [OUTPUT]
 * - SPILLOVER_MIN_CHARS: length from which the server keeps a pasted text in a file instead of the conversation.
 * - isLongPaste: whether the server keeps a text in a file (by length, or by its token pressure for CJK text).
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

/** Mirrors the server's token-pressure limit (`MAX_TOKEN_PRESSURE`), which CJK text reaches at about 4,400 characters. */
const SPILLOVER_MAX_TOKEN_PRESSURE = 8_000;

/** The server's estimate weighs a wide character (CJK, kana, hangul, fullwidth, emoji) 1.8 and any other one 0.25. */
const WIDE_CHARACTER_WEIGHT = 1.8;
const NARROW_CHARACTER_WEIGHT = 0.25;

/** East Asian wide and fullwidth characters: the main blocks of what the server's estimate counts as wide. */
const WIDE_CHARACTERS =
  /[\u1100-\u115F\u2E80-\u4DBF\u4E00-\uA4CF\uAC00-\uD7A3\uF900-\uFAFF\uFE10-\uFE19\uFE30-\uFE6B\uFF01-\uFF60\uFFE0-\uFFE6\u{17000}-\u{18CD5}\u{1B000}-\u{1B2FB}\u{1F300}-\u{1F64F}\u{1F680}-\u{1F6C5}\u{1F900}-\u{1F9FF}\u{20000}-\u{3FFFD}]/gu;

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

/** Whether the server keeps this text in a file instead of the conversation. */
export function isLongPaste(text: string): boolean {
  if (text.length > SPILLOVER_MIN_CHARS) {
    return true;
  }
  // Even all-wide text of this length stays under the token-pressure limit: skip counting on the typing path.
  if (text.length * WIDE_CHARACTER_WEIGHT <= SPILLOVER_MAX_TOKEN_PRESSURE) {
    return false;
  }
  const wide = text.match(WIDE_CHARACTERS)?.length ?? 0;
  return (
    Math.floor(wide * WIDE_CHARACTER_WEIGHT + (text.length - wide) * NARROW_CHARACTER_WEIGHT) >
    SPILLOVER_MAX_TOKEN_PRESSURE
  );
}

/** A user message that is a very long paste reads as a character count plus its opening lines, not as the whole text. */
export function pastedTextOf(text: string, spillover?: MessageSpillover): PastedText | null {
  if (spillover) {
    return { chars: spillover.chars, preview: spillover.preview };
  }
  if (isLongPaste(text)) {
    return { chars: text.length, preview: text.slice(0, SPILLOVER_PREVIEW_CHARS), fullText: text };
  }
  return null;
}

/** What a user message reads as in a title or list: a parked paste shows its opening lines, not its stored stub. */
export function userMessageDisplayText(message: Pick<Message, 'content' | 'spillover'>): string {
  return message.spillover?.preview || stripUserMessageDisplayText(message.content || '');
}
