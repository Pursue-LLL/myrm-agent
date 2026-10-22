import { describe, it, expect } from 'vitest';
import { parseAnsiString } from '../ansiParser';

describe('ansiParser', () => {
  it('returns empty array on empty or falsy string', () => {
    expect(parseAnsiString('')).toEqual([]);
  });

  it('parses plain text without ansi escape codes', () => {
    const tokens = parseAnsiString('Hello world');
    expect(tokens).toHaveLength(1);
    expect(tokens[0].text).toBe('Hello world');
    expect(tokens[0].style).toEqual({});
  });

  it('parses basic 16 foreground colors correctly', () => {
    const raw = '\x1b[31mRed text\x1b[0m and \x1b[32mGreen text\x1b[0m';
    const tokens = parseAnsiString(raw);

    expect(tokens).toHaveLength(3);
    expect(tokens[0].text).toBe('Red text');
    expect(tokens[0].style.color).toBe('#f87171');

    expect(tokens[1].text).toBe(' and ');
    expect(tokens[1].style.color).toBeUndefined();

    expect(tokens[2].text).toBe('Green text');
    expect(tokens[2].style.color).toBe('#4ade80');
  });

  it('parses SGR styles: bold, underline, italic', () => {
    const raw = '\x1b[1m\x1b[4mBold Underline\x1b[0m';
    const tokens = parseAnsiString(raw);

    expect(tokens).toHaveLength(1);
    expect(tokens[0].text).toBe('Bold Underline');
    expect(tokens[0].style.fontWeight).toBe('bold');
    expect(tokens[0].style.textDecoration).toBe('underline');
  });

  it('parses 256-color palette (38;5;n)', () => {
    const raw = '\x1b[38;5;196mBrightRed\x1b[0m';
    const tokens = parseAnsiString(raw);

    expect(tokens).toHaveLength(1);
    expect(tokens[0].text).toBe('BrightRed');
    expect(tokens[0].style.color).toBeDefined();
  });
});
