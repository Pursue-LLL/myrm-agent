import { describe, expect, it } from 'vitest';

import {
  PASTE_CARD_MIN_CHARS,
  SPILLOVER_MIN_CHARS,
  isLongPaste,
  isParkedPaste,
  normalizeSpillover,
  pastedTextOf,
  userMessageDisplayText,
} from '../spillover';

const stored = { path: '/work/.myrm/pastes/payload_1.md', chars: 48_000, preview: 'Q3 review of the roadmap' };

describe('normalizeSpillover', () => {
  it('reads the server metadata into the shape the UI uses', () => {
    expect(
      normalizeSpillover({
        spillover_path: stored.path,
        original_char_count: stored.chars,
        sha256: 'abc',
        preview: stored.preview,
      }),
    ).toEqual(stored);
  });

  it('accepts a row stored before previews were kept, with an empty preview', () => {
    expect(normalizeSpillover({ spillover_path: stored.path, original_char_count: 9 })).toEqual({
      path: stored.path,
      chars: 9,
      preview: '',
    });
  });

  it.each([undefined, null, 'x', {}, { spillover_path: '', original_char_count: 3 }, { spillover_path: 'p' }])(
    'rejects metadata that does not point at a file: %j',
    (raw) => {
      expect(normalizeSpillover(raw)).toBeUndefined();
    },
  );
});

describe('pastedTextOf', () => {
  it('describes a stored paste by its count and opening lines, with no text left to show', () => {
    expect(pastedTextOf('<file_spillover/>', stored)).toEqual({ chars: stored.chars, preview: stored.preview });
  });

  it('keeps the whole text of a long paste the server did not park, in memory or from history, so it can unfold', () => {
    const text = 'x'.repeat(PASTE_CARD_MIN_CHARS + 1);

    const pasted = pastedTextOf(text);

    expect(pasted?.chars).toBe(text.length);
    expect(pasted?.fullText).toBe(text);
    expect(pasted?.preview).toBe('x'.repeat(300));
  });

  it('leaves a text at the limit alone', () => {
    expect(pastedTextOf('x'.repeat(PASTE_CARD_MIN_CHARS))).toBeNull();
  });
});

describe('isLongPaste', () => {
  // A card folds from the same two measures as the server's, at lower limits (wide characters weigh 1.8, others 0.25,
  // token pressure 8,000); the expected sides below are what the server's estimator returns for the same texts.
  it.each([
    ['x'.repeat(PASTE_CARD_MIN_CHARS), false],
    ['x'.repeat(PASTE_CARD_MIN_CHARS + 1), true],
    ['x'.repeat(15_000), false],
    ['中'.repeat(4_444), false],
    ['中'.repeat(4_445), true],
    ['中'.repeat(5_000), true],
    ['あ'.repeat(4_445), true],
    ['한'.repeat(4_445), true],
    ['，'.repeat(4_445), true],
    ['中'.repeat(3_000) + 'x'.repeat(12_000), true],
    ['中'.repeat(2_000) + 'x'.repeat(8_000), false],
  ])('judges %#: long paste is %s', (text, expected) => {
    expect(isLongPaste(text)).toBe(expected);
  });

  it('lets a Chinese paste of that length be sent as a card while it is still in memory', () => {
    expect(pastedTextOf('中'.repeat(5_000))?.chars).toBe(5_000);
  });
});

describe('isParkedPaste', () => {
  // The server keeps the text of a person in a file past 64,000 characters or a token pressure of 16,000; the
  // expected sides below are what its estimator returns for the same texts (8,889 wide characters weigh 16,000).
  it.each([
    ['x'.repeat(SPILLOVER_MIN_CHARS), false],
    ['x'.repeat(SPILLOVER_MIN_CHARS + 1), true],
    ['x'.repeat(PASTE_CARD_MIN_CHARS + 1), false],
    ['中'.repeat(5_000), false],
    ['中'.repeat(8_889), false],
    ['中'.repeat(8_890), true],
    ['あ'.repeat(8_890), true],
    ['中'.repeat(6_000) + 'x'.repeat(40_000), true],
    ['中'.repeat(4_000) + 'x'.repeat(30_000), false],
  ])('judges %#: parked paste is %s', (text, expected) => {
    expect(isParkedPaste(text)).toBe(expected);
  });

  it('is always a card too: a text the server parks never shows whole in the bubble', () => {
    expect(PASTE_CARD_MIN_CHARS).toBeLessThan(SPILLOVER_MIN_CHARS);
    for (const text of ['x'.repeat(SPILLOVER_MIN_CHARS + 1), '中'.repeat(8_890)]) {
      expect(isParkedPaste(text) && isLongPaste(text)).toBe(true);
    }
  });
});

describe('userMessageDisplayText', () => {
  it('lists a stored paste by its opening lines', () => {
    expect(userMessageDisplayText({ content: '<file_spillover path="p"/>', spillover: stored })).toBe(stored.preview);
  });

  it('falls back to the cleaned content when the stored paste has no preview', () => {
    expect(userMessageDisplayText({ content: 'hello', spillover: { ...stored, preview: '' } })).toBe('hello');
  });

  it('cleans an ordinary message', () => {
    expect(userMessageDisplayText({ content: '<current_datetime>now</current_datetime>hello' })).toBe('hello');
  });
});
