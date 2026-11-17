import { describe, expect, it } from 'vitest';
import { firstChars } from '../firstChars';

const EMOJI = String.fromCodePoint(0x1f600);
const RARE_HAN = String.fromCodePoint(0x20bb7);

describe('firstChars', () => {
  it.each([
    ['a text shorter than the limit stays whole', 'abc', 5, 'abc'],
    ['a text of exactly the limit stays whole', 'abcde', 5, 'abcde'],
    ['a longer text is cut to the limit', 'abcdefgh', 5, 'abcde'],
    ['an empty text stays empty', '', 5, ''],
    ['a limit of zero keeps nothing', 'abc', 0, ''],
  ])('%s', (_name, text, max, expected) => {
    expect(firstChars(text, max)).toBe(expected);
  });

  it('counts an emoji or a rare han character as one character', () => {
    expect(firstChars(`${EMOJI}${RARE_HAN}${EMOJI}x`, 3)).toBe(`${EMOJI}${RARE_HAN}${EMOJI}`);
  });

  it('keeps a character that sits on the limit whole instead of splitting it', () => {
    expect(firstChars(`${'a'.repeat(79)}${EMOJI}${'b'.repeat(10)}`, 80)).toBe(`${'a'.repeat(79)}${EMOJI}`);
  });

  it('keeps exactly the limit when every character takes two UTF-16 units', () => {
    const cut = firstChars(RARE_HAN.repeat(300), 200);

    expect(Array.from(cut)).toHaveLength(200);
    expect(cut).toBe(RARE_HAN.repeat(200));
  });

  it('cuts at the same place as counting every character of the whole text', () => {
    const mixed = `ab${EMOJI}中${RARE_HAN}c`.repeat(40);

    for (let max = 0; max <= 60; max += 1) {
      expect(firstChars(mixed, max)).toBe(Array.from(mixed).slice(0, max).join(''));
    }
  });
});
