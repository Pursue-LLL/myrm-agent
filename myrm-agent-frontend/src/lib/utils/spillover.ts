/**
 * [INPUT]
 * - @/store/chat/types::Message, MessageSpillover (POS: Chat message entity)
 * - ./messageUtils::stripUserMessageDisplayText (POS: Message text cleanup helpers)
 *
 * [OUTPUT]
 * - PASTE_CARD_MIN_CHARS: length from which a pasted text folds into a card in the user bubble.
 * - SPILLOVER_MIN_CHARS: length from which the server keeps a pasted text in a file instead of the conversation.
 * - estimateTokenPressure: the server's token estimate of a text, which weighs each character by its kind.
 * - isLongPaste: whether a text folds into a card (by length, or by its token pressure).
 * - isParkedPaste: whether the server keeps a text in a file (by the same two measures, at higher limits).
 * - normalizeSpillover: the persisted `spillover` metadata of a history message, or undefined.
 * - pastedTextOf: the collapsed form of a user message that is a long paste, or null.
 * - userMessageDisplayText: the text a user message is listed by (titles, turn rail).
 *
 * [POS]
 * Pasted-text helpers shared by the composer notice, the user bubble and the places that list a message by its text.
 * Two lines apart: a text folds into a card in the bubble long before the server stops sending it to the model whole,
 * so a card can hold the full text (copy and edit stay) and only a parked one points at a file.
 */
import type { Message, MessageSpillover } from '@/store/chat/types';
import { stripUserMessageDisplayText } from './messageUtils';

/** A text folds into a card in the bubble from this length: how the chat looks, not what the model receives. */
export const PASTE_CARD_MIN_CHARS = 16_000;

/** The token pressure from which a text folds into a card, which CJK text reaches at about 4,400 characters. */
const PASTE_CARD_MAX_TOKEN_PRESSURE = 8_000;

/** Mirrors the server's message size limit for the text of a person (`USER_TEXT_LIMITS`); longer pastes are kept in a file. */
export const SPILLOVER_MIN_CHARS = 64_000;

/** Mirrors the server's token-pressure limit for the text of a person (`USER_TEXT_LIMITS`), which CJK text reaches at about 8,900 characters. */
const SPILLOVER_MAX_TOKEN_PRESSURE = 16_000;

/**
 * What one character adds to the server's estimate (`estimate_token_pressure`), in hundredths of a token. Whole
 * numbers keep the sum exact, so it rounds the same way here as on the server.
 */
const PLAIN_CENTI_WEIGHT = 25; // a lowercase letter or white space
const SYMBOL_CENTI_WEIGHT = 40; // any other ASCII character
const DIGIT_CENTI_WEIGHT = 75;
const UPPER_CENTI_WEIGHT = 100;
const ALPHABET_CENTI_WEIGHT = 50; // a non-ASCII narrow character: Cyrillic, Arabic, Indic, Thai, accented Latin
const WIDE_CENTI_WEIGHT = 180; // CJK, kana, hangul, fullwidth, emoji

const ASCII_CENTI_WEIGHTS = Uint8Array.from({ length: 128 }, (_, code) => {
  const char = String.fromCharCode(code);
  if (/[a-z \t\n\r]/.test(char)) {
    return PLAIN_CENTI_WEIGHT;
  }
  if (/[A-Z]/.test(char)) {
    return UPPER_CENTI_WEIGHT;
  }
  return /[0-9]/.test(char) ? DIGIT_CENTI_WEIGHT : SYMBOL_CENTI_WEIGHT;
});

/** East Asian wide and fullwidth characters: the main blocks of what the server's estimate counts as wide. */
const WIDE_CHARACTERS =
  /[\u1100-\u115F\u2E80-\u4DBF\u4E00-\uA4CF\uAC00-\uD7A3\uF900-\uFAFF\uFE10-\uFE19\uFE30-\uFE6B\uFF01-\uFF60\uFFE0-\uFFE6\u{17000}-\u{18CD5}\u{1B000}-\u{1B2FB}\u{1F300}-\u{1F64F}\u{1F680}-\u{1F6C5}\u{1F900}-\u{1F9FF}\u{20000}-\u{3FFFD}]/gu;

/** Mirrors the server's preview length (`ContextGuardConfig.preview_chars`). */
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

/** The server's `estimate_token_pressure` for a text: each character weighs by its kind. */
export function estimateTokenPressure(text: string): number {
  let centi = 0;
  let nonAscii = 0;
  for (let i = 0; i < text.length; i += 1) {
    const code = text.charCodeAt(i);
    if (code < 128) {
      centi += ASCII_CENTI_WEIGHTS[code];
    } else {
      nonAscii += 1;
      // A surrogate pair is one character.
      const next = code >= 0xd800 && code <= 0xdbff ? text.charCodeAt(i + 1) : 0;
      if (next >= 0xdc00 && next <= 0xdfff) {
        i += 1;
      }
    }
  }
  if (nonAscii > 0) {
    const wide = text.match(WIDE_CHARACTERS)?.length ?? 0;
    centi += wide * WIDE_CENTI_WEIGHT + (nonAscii - wide) * ALPHABET_CENTI_WEIGHT;
  }
  return Math.floor(centi / 100);
}

/** Whether a text is past a limit by length or by the server's token-pressure estimate. */
function exceeds(text: string, maxChars: number, maxTokenPressure: number): boolean {
  if (text.length > maxChars) {
    return true;
  }
  // Even all-wide text of this length stays under the token-pressure limit: skip counting on the typing path.
  if (text.length * WIDE_CENTI_WEIGHT <= maxTokenPressure * 100) {
    return false;
  }
  return estimateTokenPressure(text) > maxTokenPressure;
}

/** Whether a text is long enough to fold into a card in the user bubble; the model still receives it whole. */
export function isLongPaste(text: string): boolean {
  return exceeds(text, PASTE_CARD_MIN_CHARS, PASTE_CARD_MAX_TOKEN_PRESSURE);
}

/** Whether the server keeps this text in a file instead of the conversation. */
export function isParkedPaste(text: string): boolean {
  return exceeds(text, SPILLOVER_MIN_CHARS, SPILLOVER_MAX_TOKEN_PRESSURE);
}

/** A user message that is a long paste reads as a character count plus its opening lines, not as the whole text. */
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
