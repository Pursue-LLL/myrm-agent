import { describe, expect, it } from 'vitest';

import { lineAt, parseProgram } from '../source-ast';

describe('lineAt', () => {
  it('counts every line terminator TypeScript counts, with CRLF as one', () => {
    const source = 'a\r\nb\nc\rd\u2028e\u2029f';
    expect([0, 3, 5, 7, 9, 11].map((offset) => lineAt(source, offset))).toEqual([1, 2, 3, 4, 5, 6]);
  });
});

describe('parseProgram', () => {
  it('throws on a syntax error instead of returning a partial tree', () => {
    expect(() => parseProgram('const = ;', 'broken.ts')).toThrow('Cannot parse broken.ts');
  });

  it('parses JSX only for .tsx / .jsx file names', () => {
    expect(() => parseProgram('const view = <div />;', 'view.tsx')).not.toThrow();
    expect(() => parseProgram('const view = <div />;', 'view.ts')).toThrow();
  });
});
