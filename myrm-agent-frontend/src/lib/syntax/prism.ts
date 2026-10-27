/**
 * Prism with the grammars the product relies on, shared by every syntax-highlighted surface.
 *
 * [INPUT]
 * - prism-react-renderer::Prism (POS: the highlighter's own Prism instance, which ships 28 grammars)
 * - prismjs/components/prism-*: (POS: grammar definitions, each a script that registers itself on the global `Prism`)
 *
 * [OUTPUT]
 * - Prism: that same instance with bash (also sh, shell, zsh), diff, java, ruby, csharp, toml, lua, r, php and dart added
 * - MAX_HIGHLIGHT_LINE_CHARS: the longest line a text may have and still be coloured
 * - resolveLanguage: the language to hand to a highlighter, `text` when there is nothing to colour the text with
 *
 * [POS]
 * The one place a Prism grammar is added, so a language named in `EXT_TO_LANGUAGE`, in a Markdown fence or by a tool
 * always has a grammar behind it, and the one place that decides a text is too risky to colour. Consumers take `Prism`
 * and `resolveLanguage` from here instead of from prism-react-renderer, which makes the registration a dependency they
 * cannot forget.
 */
import { Prism } from 'prism-react-renderer';

// The grammar files read a global `Prism`, so it has to exist before the first of them runs. They are required here, in
// statement order, rather than imported: package.json lists only CSS under "sideEffects", so a module that exists just
// to set the global is dropped from a production build, and then the grammars register nothing without any error.
(globalThis as { Prism?: typeof Prism }).Prism = Prism;

// scss is left out on purpose: its grammar needs 11 s for a 50,000-character data URI where css, which it extends,
// needs 1 ms, so every stylesheet with an inline image would freeze the page.
require('prismjs/components/prism-bash');
require('prismjs/components/prism-diff');
require('prismjs/components/prism-java');
require('prismjs/components/prism-ruby');
require('prismjs/components/prism-csharp');
require('prismjs/components/prism-toml');
require('prismjs/components/prism-lua');
require('prismjs/components/prism-r');
require('prismjs/components/prism-markup-templating');
require('prismjs/components/prism-php');
require('prismjs/components/prism-dart');

// prism-bash names itself bash, sh and shell; zsh is the one shell people fence that it leaves out.
Prism.languages.zsh = Prism.languages.bash;

export { Prism };

/**
 * Grammars are backtracking regular expressions, and on one very long line many of them take time that grows with the
 * square of its length. For a bare base64 line of 10,000 and of 100,000 characters: markdown 36 ms and 3.4 s, lua 219 ms
 * and 22 s, typescript 654 ms at 10,000 (the 100,000 run was skipped), css 130 ms and 13 s when the line is an unclosed
 * string. The same characters cut into 80-character lines stay under 0.5 s at 100,000 (css apart). Minified code and embedded data are the
 * usual such lines, and colouring them has little value, so a text with a line past this is left uncoloured.
 */
export const MAX_HIGHLIGHT_LINE_CHARS = 10_000;

function hasLongLine(code: string): boolean {
  for (let start = 0; ;) {
    const end = code.indexOf('\n', start);
    if ((end === -1 ? code.length : end) - start > MAX_HIGHLIGHT_LINE_CHARS) {
      return true;
    }
    if (end === -1) {
      return false;
    }
    start = end + 1;
  }
}

/**
 * The language to colour with: `text`, Prism's name for "nothing to colour", when the language is missing, unknown or
 * `text`, and, if the text to colour is given, when it has a line longer than MAX_HIGHLIGHT_LINE_CHARS.
 */
export function resolveLanguage(language: string | undefined, code?: string): string {
  if (language === undefined || language === 'text' || !Prism.languages[language]) {
    return 'text';
  }
  return code !== undefined && hasLongLine(code) ? 'text' : language;
}
