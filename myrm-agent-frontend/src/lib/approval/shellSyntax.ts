/**
 * Which characters of a shell command the shell itself interprets.
 *
 * Mirror of harness `core/security/shell_command_lexer.py::iter_syntax_chars`.
 * Keep the parity vectors in `__tests__/shellCommandDisplay.test.ts` aligned with the harness tests.
 */

/** Reported last when the text ends inside a quote or after a dangling backslash. */
export const UNTERMINATED = '\0';

/** A comment starts only at the beginning of a word: after a blank or an operator. */
const WORD_BREAKS = ' \t\n\r|;&';
const ESCAPABLE_IN_DOUBLE_QUOTES = '$`"\\\n';
const EXPANDING_IN_DOUBLE_QUOTES = '$`';

export type SyntaxChar = readonly [index: number, char: string];

/**
 * Every character the shell interprets, with its index: everything outside quotes, escapes and comments, plus
 * the `$` and backtick that still expand inside double quotes. A quote that never closes, or a trailing
 * backslash, adds `UNTERMINATED` last.
 */
export function listSyntaxChars(command: string): SyntaxChar[] {
  const found: SyntaxChar[] = [];
  // The opener of the quote being read: `'`, `"` or `$'` (ANSI-C, where a backslash escapes the closing `'`).
  let quote = '';
  let atWordStart = true;
  let dollarEnd = -1; // index right after an unquoted `$` that no `$$` has taken for the process id
  let index = 0;

  while (index < command.length) {
    const char = command[index];
    if (char === '\\' && quote !== "'") {
      const following = command.charAt(index + 1);
      if (!following) {
        found.push([command.length, UNTERMINATED]);
        return found;
      }
      if (following === '\n') {
        index += 2;
        continue;
      }
      index += quote === '"' && !ESCAPABLE_IN_DOUBLE_QUOTES.includes(following) ? 1 : 2;
      atWordStart = false;
    } else if (quote) {
      if (char === quote.slice(-1)) {
        quote = '';
      } else if (quote === '"' && EXPANDING_IN_DOUBLE_QUOTES.includes(char)) {
        found.push([index, char]);
      }
      index += 1;
    } else if (char === "'" || char === '"') {
      quote = char === "'" && dollarEnd === index ? "$'" : char;
      atWordStart = false;
      index += 1;
    } else if (char === '#' && atWordStart) {
      const lineEnd = command.indexOf('\n', index);
      index = lineEnd < 0 ? command.length : lineEnd;
    } else {
      found.push([index, char]);
      atWordStart = WORD_BREAKS.includes(char);
      if (char !== '$') {
        dollarEnd = -1;
      } else {
        // `$$` is the process id, so a quote opens ANSI-C only after an odd number of dollars.
        dollarEnd = dollarEnd === index ? -1 : index + 1;
      }
      index += 1;
    }
  }

  if (quote) {
    found.push([command.length, UNTERMINATED]);
  }
  return found;
}
