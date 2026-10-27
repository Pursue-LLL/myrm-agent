import { describe, expect, it } from 'vitest';

import {
  SPILLOVER_MIN_CHARS,
  isLongPaste,
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

  it('keeps the whole text of a long paste still in memory so it can unfold', () => {
    const text = 'x'.repeat(SPILLOVER_MIN_CHARS + 1);

    const pasted = pastedTextOf(text);

    expect(pasted?.chars).toBe(text.length);
    expect(pasted?.fullText).toBe(text);
    expect(pasted?.preview).toBe('x'.repeat(300));
  });

  it('leaves a text at the limit alone', () => {
    expect(pastedTextOf('x'.repeat(SPILLOVER_MIN_CHARS))).toBeNull();
  });
});

describe('isLongPaste', () => {
  // The server measures a text by length and by token pressure (wide characters weigh 1.8, others 0.25, limit 8,000);
  // the expected sides below are what its estimator returns for the same texts.
  it.each([
    ['x'.repeat(SPILLOVER_MIN_CHARS), false],
    ['x'.repeat(SPILLOVER_MIN_CHARS + 1), true],
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
