import { describe, expect, it } from 'vitest';
import { ApiError } from '@/lib/api';
import {
  appendToComposer,
  buildTerminalSnippet,
  classifyTerminalFailure,
  MAX_INJECTED_OUTPUT_CHARS,
} from '../tabs/terminalOutput';

const MARKER = '[earlier output omitted]';
const snippet = (output: string, command = 'ls') => buildTerminalSnippet({ command, output, omittedMarker: MARKER });

describe('buildTerminalSnippet', () => {
  it('fences the command and its output', () => {
    expect(snippet('a.txt\nb.txt\n')).toBe('```bash\n$ ls\na.txt\nb.txt\n```');
  });

  it('keeps the whole output when it is exactly at the limit', () => {
    const output = 'x'.repeat(MAX_INJECTED_OUTPUT_CHARS);

    expect(snippet(output)).toContain(output);
    expect(snippet(output)).not.toContain(MARKER);
  });

  it('keeps only the tail of a long output and says the start was left out', () => {
    const output = `HEAD-${'x'.repeat(MAX_INJECTED_OUTPUT_CHARS)}-TAIL`;

    const result = snippet(output);

    expect(result).toContain(MARKER);
    expect(result).toContain('-TAIL');
    expect(result).not.toContain('HEAD-');
    expect(result.split('\n')[2]).toBe(MARKER);
    expect(result.length).toBeLessThan(MAX_INJECTED_OUTPUT_CHARS + 100);
  });

  it('starts the kept tail on a whole line when a line break is close to the cut', () => {
    const lines = Array.from({ length: 2000 }, (_, index) => `line ${index}`).join('\n');

    const body = snippet(lines).split('\n').slice(3, -1);

    expect(body[0]).toMatch(/^line \d+$/);
    expect(body[body.length - 1]).toBe('line 1999');
  });

  it('never starts the kept tail in the middle of a character', () => {
    // The odd-length suffix makes the cut fall between the two halves of an emoji.
    const output = `${'😀'.repeat(MAX_INJECTED_OUTPUT_CHARS)}z`;

    const kept = snippet(output).split('\n')[3];

    expect(kept.codePointAt(0)).toBe(0x1f600);
  });

  it('uses a fence longer than any backtick run in the text so the text cannot close it', () => {
    const result = snippet('```\ninner\n```', 'cat README.md');

    expect(result.startsWith('````bash\n')).toBe(true);
    expect(result.endsWith('\n````')).toBe(true);
  });
});

describe('appendToComposer', () => {
  it('starts the composer with the snippet when it is empty or blank', () => {
    expect(appendToComposer('', 'S')).toBe('S\n');
    expect(appendToComposer('  \n ', 'S')).toBe('S\n');
  });

  it('keeps what the user typed and separates the snippet with a blank line', () => {
    expect(appendToComposer('why?  \n', 'S')).toBe('why?\n\nS\n');
  });
});

describe('classifyTerminalFailure', () => {
  it.each([
    [new ApiError('x', 400), 'blocked'],
    [new ApiError('x', 404), 'workspaceUnavailable'],
    [new ApiError('x', 408), 'timedOut'],
    [new ApiError('x', 40408, [], undefined, 'TIMEOUT_ERROR'), 'timedOut'],
    [new ApiError('x', 500), 'failed'],
    [new ApiError('x', 503, [], undefined, 'BACKEND_UNREACHABLE'), 'failed'],
    [new Error('boom'), 'failed'],
    ['boom', 'failed'],
  ])('maps %o to %s', (error, kind) => {
    expect(classifyTerminalFailure(error)).toBe(kind);
  });
});
