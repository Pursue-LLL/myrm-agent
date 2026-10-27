import { describe, expect, it } from 'vitest';

import { EXT_TO_LANGUAGE } from '@/lib/diff/parseUnifiedDiff';
import { MAX_HIGHLIGHT_LINE_CHARS, Prism, resolveLanguage } from '../prism';

/** One snippet per grammar the registry adds, each with something the grammar can tell apart from plain text. */
const SNIPPETS: ReadonlyArray<readonly [string, string]> = [
  ['bash', 'if [ -f "$f" ]; then echo "$HOME"; fi # done'],
  ['diff', '@@ -1,2 +1,2 @@\n-old\n+new\n'],
  ['java', 'public class A { private final String s = "x"; }'],
  ['ruby', 'def greet(name)\n  puts "hi #{name}"\nend'],
  ['csharp', 'public class A { private readonly string s = "x"; }'],
  ['toml', '[server]\nport = 8080\n'],
  ['lua', 'local x = 1\nfunction f() return x end'],
  ['r', 'x <- c(1, 2, 3)\nprint(x)'],
  ['php', '<?php echo "hi"; ?>'],
  ['dart', 'void main() { print("hi"); }'],
];

/** Anything that is not a bare string is a token the grammar recognised. */
function recognisedTokens(code: string, language: string): number {
  const grammar = Prism.languages[language];
  if (!grammar) {
    throw new Error(`no grammar registered for ${language}`);
  }
  return Prism.tokenize(code, grammar).filter((piece) => typeof piece !== 'string').length;
}

describe('grammars the shared Prism registry adds', () => {
  it.each(SNIPPETS)('%s is registered and recognises its own syntax', (language, code) => {
    expect(recognisedTokens(code, language)).toBeGreaterThan(0);
  });

  it.each(['sh', 'shell', 'zsh'])('%s is another name for bash', (alias) => {
    expect(Prism.languages[alias]).toBe(Prism.languages.bash);
  });

  it('keeps the grammars prism-react-renderer ships', () => {
    for (const language of ['typescript', 'python', 'json', 'markdown', 'yaml']) {
      expect(Prism.languages[language]).toBeDefined();
    }
  });
});

describe('resolveLanguage', () => {
  it('keeps a language that has a grammar', () => {
    expect(resolveLanguage('typescript')).toBe('typescript');
    expect(resolveLanguage('bash')).toBe('bash');
    expect(resolveLanguage('diff')).toBe('diff');
  });

  it('falls back to text for a missing, unknown or empty language', () => {
    expect(resolveLanguage(undefined)).toBe('text');
    expect(resolveLanguage('')).toBe('text');
    expect(resolveLanguage('no-such-language')).toBe('text');
  });

  it('treats text as "nothing to colour"', () => {
    expect(resolveLanguage('text')).toBe('text');
  });
});

describe('resolveLanguage for a given text', () => {
  const line = (length: number): string => 'a'.repeat(length);

  it('colours text whose lines are all within the limit, however long the text is', () => {
    expect(resolveLanguage('typescript', line(MAX_HIGHLIGHT_LINE_CHARS))).toBe('typescript');
    expect(resolveLanguage('typescript', `${line(MAX_HIGHLIGHT_LINE_CHARS)}\n`.repeat(20))).toBe('typescript');
    expect(resolveLanguage('typescript', '')).toBe('typescript');
  });

  it('leaves text with a longer line uncoloured, wherever the line is', () => {
    const tooLong = line(MAX_HIGHLIGHT_LINE_CHARS + 1);
    expect(resolveLanguage('typescript', tooLong)).toBe('text');
    expect(resolveLanguage('typescript', `short\n${tooLong}\nshort`)).toBe('text');
    expect(resolveLanguage('typescript', `short\r\n${tooLong}\r\n`)).toBe('text');
    expect(resolveLanguage('typescript', `${tooLong}\nshort`)).toBe('text');
  });

  it('still answers text for a language with no grammar', () => {
    expect(resolveLanguage('no-such-language', 'short')).toBe('text');
  });
});

describe('file extension mapping', () => {
  it('only names languages that can be coloured, so no extension is mapped to a grammar that does not exist', () => {
    const unusable = Object.entries(EXT_TO_LANGUAGE)
      .filter(([, language]) => resolveLanguage(language) !== language)
      .map(([extension, language]) => `${extension} -> ${language}`);
    expect(unusable).toEqual([]);
  });
});
