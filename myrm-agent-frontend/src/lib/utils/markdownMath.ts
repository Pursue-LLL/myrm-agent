/**
 * Math in markdown text: the one pipeline every surface that renders assistant output shares.
 *
 * [INPUT]
 * - markdown from a model: `$…$`, `$$…$$`, `\(…\)` and `\[…\]` formulas next to prices, shell variables and code
 *
 * [OUTPUT]
 * - normalizeMathDelimiters: the text pre-pass, run before parsing
 * - mathPlugins, chatMathPlugins: remark and rehype plugin lists for react-markdown and unified processors; the chat
 *   list differs in the KaTeX options and in unwrapping SVG that a message's raw HTML carries
 *
 * [POS]
 * What counts as a formula is decided once, inside the parser (`remarkMathPolicy`): a `$` the policy refuses stays
 * literal text and can still open the next formula. Guessing in the text before the parser cannot do that, because
 * the parser pairs the `$` again afterwards and disagrees with the guess. The pre-pass therefore only does what the
 * parser cannot see: turn `\(…\)` / `\[…\]` into `$` delimiters and guard an unfinished `$$` while streaming.
 */
import type { Element, Root as HastRoot } from 'hast';
import type { Root as MdastRoot } from 'mdast';
import { mathFromMarkdown } from 'mdast-util-math';
import { math } from 'micromark-extension-math';
import type { Code, Extension, TokenizeContext } from 'micromark-util-types';
import rehypeKatex from 'rehype-katex';
import type { Options as KatexOptions } from 'rehype-katex';
// Type-only: makes the micromark extension slots of `this.data()` known to TypeScript.
import type {} from 'remark-parse';
import type { PluggableList, Plugin } from 'unified';
import { visit } from 'unist-util-visit';

const DOLLAR = 36;

/** Chinese, Japanese and Korean letters and full-width punctuation. */
const CJK = /[\u2E80-\u9FFF\uAC00-\uD7AF\uF900-\uFAFF\uFF00-\uFFEF]/;
const isAsciiDigit = (code: Code): boolean => code !== null && code >= 48 && code <= 57;

/**
 * Whether the single-`$` span the parser just read is not a formula. Only `$…$` is judged, `$$…$$` is left alone.
 * Models use `$` for prices, shell variables and money in prose far more often than the stock parser rules expect:
 * 1. a digit right after the closing `$` (`$20,000 and $30,000`): Pandoc's `tex_math_dollars` rule;
 * 2. a backtick inside the span (`$HOME … \`echo $HOME\``): code wins over math;
 * 3. an opening `$` followed by text while the closing `$` follows whitespace (`$JAVA_HOME and $PATH`, `$5 + 3 $`):
 *    Pandoc's closing rule; the symmetric padded form `$ x $` stays a formula;
 * 4. a span that starts with a digit and ends with a CJK character: Chinese text has no spaces, so in
 *    `存入$1,000，利率$r$` the price's `$` would pair with the formula's opener.
 */
function isNotMath(context: TokenizeContext, codeAfterCloser: Code): boolean {
  const span = context.events.at(-1)?.[1];
  if (span?.type !== 'mathText') {
    return false;
  }
  const source = context.sliceSerialize(span);
  if (source.startsWith('$$')) {
    return false;
  }
  const inner = source.slice(1, -1);
  if (isAsciiDigit(codeAfterCloser) || inner.includes('`')) {
    return true;
  }
  if (!/^[ \t\r\n]/.test(inner) && /[ \t\r\n]$/.test(inner)) {
    return true;
  }
  return /^\d/.test(inner) && CJK.test(inner.at(-1) ?? '');
}

const stockMath = math({ singleDollarTextMath: true });
const stockText = stockMath.text?.[DOLLAR];
if (!stockText || Array.isArray(stockText)) {
  throw new Error('micromark-extension-math no longer exposes a single `$` text construct');
}

const policyExtension: Extension = {
  flow: stockMath.flow,
  text: {
    [DOLLAR]: {
      ...stockText,
      tokenize(effects, ok, nok) {
        // Refusing with `nok` rewinds the parser: the opening `$` becomes plain text and parsing resumes right
        // after it, so the refused closing `$` is still free to open the next formula.
        return stockText.tokenize.call(this, effects, (code) => (isNotMath(this, code) ? nok(code) : ok(code)), nok);
      },
    },
  },
};

/**
 * Math syntax for remark: the `$` / `$$` micromark extension with the single-`$` policy above, and the conversion
 * of its tokens into `math` / `inlineMath` nodes.
 */
const remarkMathPolicy: Plugin<[], MdastRoot> = function () {
  const data = this.data();
  (data.micromarkExtensions ??= []).push(policyExtension);
  (data.fromMarkdownExtensions ??= []).push(mathFromMarkdown());
};

/**
 * `%` opens a TeX comment and would swallow the rest of the formula, yet models write percentages inside formulas
 * (`$$50% \text{done}$$`). Only the nodes the math parser produced are touched, so code and prose keep their `%`.
 */
const rehypeEscapeMathPercent: Plugin<[], HastRoot> = () => (tree) => {
  // The visitor must not return a value: `false` would stop the walk and a number would jump to that index.
  visit(tree, 'element', (node: Element) => {
    const classNames = node.properties.className;
    if (node.tagName !== 'code' || !Array.isArray(classNames) || !classNames.includes('language-math')) {
      return;
    }
    for (const child of node.children) {
      if (child.type === 'text') {
        child.value = child.value.replace(/(?<!\\)%/g, '\\%');
      }
    }
  });
};

const VECTOR_TAGS = new Set(['svg', 'path', 'line']);

/**
 * Chat messages let `svg`, `path` and `line` through their element whitelist, because KaTeX draws roots, vectors,
 * braces and arrows with them. SVG a model writes itself is not wanted there, so this unwraps it to its content, the
 * way the whitelist treats every other element it refuses. It has to run on the tree `rehypeRaw` produced and before
 * KaTeX renders: KaTeX's own SVG is then the only SVG that reaches the whitelist.
 */
const rehypeUnwrapRawVector: Plugin<[], HastRoot> = () => (tree) => {
  visit(tree, 'element', (node: Element, index, parent) => {
    if (!VECTOR_TAGS.has(node.tagName) || !parent || index === undefined) {
      return;
    }
    parent.children.splice(index, 1, ...node.children);
    // The spliced-in children now sit at this index, and visiting resumes there, so nested vector tags go too.
    return index;
  });
};

/**
 * What chat messages render with: html-only output, no strict-mode warnings, and KaTeX's trusted commands enabled.
 * `throwOnError` is absent on purpose: rehype-katex sets it itself and falls back to KaTeX's inline error markup.
 */
const chatKatexOptions: KatexOptions = {
  strict: false,
  output: 'html',
  trust: true,
};

/** Plugin lists for `react-markdown` (`remarkPlugins`, `rehypePlugins`) and unified processors alike. */
interface MathPlugins {
  remark: PluggableList;
  rehype: PluggableList;
}

const remarkPlugins: PluggableList = [remarkMathPolicy];

/**
 * For everything that is not a chat message (compacted summaries, archived messages, document previews, the HTML
 * export): KaTeX with its own defaults, so the commands that link or load a resource (`\href`, `\includegraphics`,
 * `\htmlClass`) stay switched off.
 */
export const mathPlugins: MathPlugins = {
  remark: remarkPlugins,
  rehype: [rehypeEscapeMathPercent, rehypeKatex],
};

/**
 * For chat messages: the KaTeX options above, and the unwrapping of SVG the model wrote. The list has to run after
 * `rehypeRaw`, which turns the raw HTML of a message into elements.
 */
export const chatMathPlugins: MathPlugins = {
  remark: remarkPlugins,
  rehype: [rehypeUnwrapRawVector, rehypeEscapeMathPercent, [rehypeKatex, chatKatexOptions]],
};

/** Fenced code (up to its closing fence, or to the end while a stream has not closed it) and inline code spans. */
const CODE_RE = /(`{3,}|~{3,})[\s\S]*?(?:\1|$)|`[^`\n]+`/g;

/** An unfinished `$$` makes KaTeX flash an error on every streamed frame, so the last unpaired one is escaped. */
function escapeIncompleteBlockMath(text: string): string {
  const parts = text.split('$$');
  if (parts.length % 2 === 0) {
    const lastIndex = text.lastIndexOf('$$');
    return text.slice(0, lastIndex) + '\\$\\$' + text.slice(lastIndex + 2);
  }
  return text;
}

/** A placeholder prefix that does not occur in the text, so restoring can never touch the author's own words. */
function uniquePlaceholderTag(content: string): string {
  let tag = 'MATHCODE';
  while (content.includes(tag)) {
    tag += '_';
  }
  return tag;
}

/**
 * Text pre-pass for what the parser cannot see: `\[…\]` becomes `$$…$$`, `\(…\)` becomes `$…$`, and while streaming
 * the last unpaired `$$` is escaped. Code is lifted out first and put back verbatim, so it is never rewritten.
 */
export function normalizeMathDelimiters(content: string, isStreaming = false): string {
  if (!content.includes('\\') && !(isStreaming && content.includes('$$'))) {
    return content;
  }

  const tag = uniquePlaceholderTag(content);
  const codeSpans: string[] = [];
  let text = content.replace(CODE_RE, (code) => `${tag}${codeSpans.push(code) - 1}_`);

  text = text
    .replace(/\\\[([\s\S]*?)\\\]/g, (_match, inner: string) => `$$${inner}$$`)
    // The padding models put inside `\( … \)` must not reach the `$`: a padded closer is refused by rule 3.
    .replace(/\\\((.+?)\\\)/g, (match, inner: string) => {
      const formula = inner.trim();
      return formula ? `$${formula}$` : match;
    });
  if (isStreaming) {
    text = escapeIncompleteBlockMath(text);
  }

  // A function replacer keeps `$&`, `$'` and `$$` inside the restored code from being expanded as patterns.
  return text.replace(new RegExp(`${tag}(\\d+)_`, 'g'), (_placeholder, index: string) => codeSpans[Number(index)]);
}
