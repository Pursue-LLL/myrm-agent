/**
 * Web Terminal ANSI Emulator Unit Tests
 */

import { describe, expect, it } from 'vitest';
import {
  appendRawChunkToLines,
  mapKeyToControlSequence,
  parseAnsiChunkToSegments,
} from '../webTerminalAnsiEmulator';

describe('webTerminalAnsiEmulator', () => {
  it('should map keys to standard control codes properly', () => {
    expect(mapKeyToControlSequence('c', true)).toBe('\x03'); // Ctrl+C (SIGINT)
    expect(mapKeyToControlSequence('d', true)).toBe('\x04'); // Ctrl+D (EOF)
    expect(mapKeyToControlSequence('z', true)).toBe('\x1a'); // Ctrl+Z (SIGTSTP)
    expect(mapKeyToControlSequence('l', true)).toBe('\x0c'); // Ctrl+L (Clear)

    expect(mapKeyToControlSequence('Enter')).toBe('\r');
    expect(mapKeyToControlSequence('Backspace')).toBe('\b');
    expect(mapKeyToControlSequence('Tab')).toBe('\t');
    expect(mapKeyToControlSequence('ArrowUp')).toBe('\x1b[A');
    expect(mapKeyToControlSequence('ArrowDown')).toBe('\x1b[B');
    expect(mapKeyToControlSequence('a')).toBe('a');
  });

  it('should parse ANSI color codes into styled segments', () => {
    // \x1b[32mHello\x1b[0m \x1b[31;1mWorld\x1b[0m
    const rawAnsi = '\x1b[32mHello\x1b[0m \x1b[31;1mWorld\x1b[0m';
    const segments = parseAnsiChunkToSegments(rawAnsi);

    expect(segments.length).toBeGreaterThanOrEqual(3);
    expect(segments[0].text).toBe('Hello');
    expect(segments[0].style.color).toBe('#4ade80'); // green

    expect(segments[1].text).toBe(' ');

    expect(segments[2].text).toBe('World');
    expect(segments[2].style.color).toBe('#f87171'); // red
    expect(segments[2].style.bold).toBe(true);
  });

  it('should append raw chunk to lines and honor maxLines limit', () => {
    const lines = appendRawChunkToLines([], 'Line 1\nLine 2\nLine 3', 2);
    expect(lines.length).toBe(2);
    expect(lines[0].segments[0].text).toBe('Line 2');
    expect(lines[1].segments[0].text).toBe('Line 3');
  });

  it('should clear buffer on form feed control character', () => {
    const existing = appendRawChunkToLines([], 'Some output');
    expect(existing.length).toBeGreaterThan(0);

    const cleared = appendRawChunkToLines(existing, '\x0c');
    expect(cleared).toHaveLength(0);
  });
});
