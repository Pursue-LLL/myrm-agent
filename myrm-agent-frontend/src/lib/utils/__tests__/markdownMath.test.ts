import rehypeRaw from 'rehype-raw';
import rehypeStringify from 'rehype-stringify';
import remarkGfm from 'remark-gfm';
import remarkParse from 'remark-parse';
import remarkRehype from 'remark-rehype';
import { unified } from 'unified';
import { visit } from 'unist-util-visit';
import { describe, expect, it } from 'vitest';
import { chatMathPlugins, mathPlugins, normalizeMathDelimiters } from '../markdownMath';

const parser = unified().use(remarkParse).use(remarkGfm).use(mathPlugins.remark);

function rendererFor(preset: typeof mathPlugins) {
  return unified()
    .use(remarkParse)
    .use(remarkGfm)
    .use(preset.remark)
    .use(remarkRehype)
    .use(preset.rehype)
    .use(rehypeStringify);
}
const renderer = rendererFor(mathPlugins);
const chatRenderer = rendererFor(chatMathPlugins);

/** Everything the parser makes of a text after the pre-pass: formula sources, and the literal text left over. */
function parse(markdown: string): { formulas: string[]; text: string } {
  const formulas: string[] = [];
  const texts: string[] = [];
  visit(parser.parse(normalizeMathDelimiters(markdown)), (node) => {
    if (node.type === 'inlineMath' || node.type === 'math') {
      formulas.push(node.value);
    }
    if (node.type === 'text' || node.type === 'inlineCode' || node.type === 'code') {
      texts.push(node.value);
    }
  });
  return { formulas, text: texts.join('') };
}

const render = (markdown: string): string => String(renderer.processSync(normalizeMathDelimiters(markdown)));
const renderChat = (markdown: string): string => String(chatRenderer.processSync(normalizeMathDelimiters(markdown)));

describe('normalizeMathDelimiters', () => {
  describe('LaTeX delimiters', () => {
    it('converts \\[...\\] to $$...$$', () => {
      const result = normalizeMathDelimiters('The answer is \\[x = \\frac{-b}{2a}\\] done.');
      expect(result).toBe('The answer is $$x = \\frac{-b}{2a}$$ done.');
    });

    it('converts \\(...\\) to $...$', () => {
      expect(normalizeMathDelimiters('Inline formula \\(E = mc^2\\) here.')).toBe('Inline formula $E = mc^2$ here.');
    });

    it('converts a multiline \\[...\\]', () => {
      const input = '\\[\n\\begin{aligned}\nx &= 1 \\\\\ny &= 2\n\\end{aligned}\n\\]';
      expect(normalizeMathDelimiters(input)).toBe('$$\n\\begin{aligned}\nx &= 1 \\\\\ny &= 2\n\\end{aligned}\n$$');
    });

    it('converts several formulas in one text', () => {
      const input = 'Given \\(a > 0\\) and \\[x^2 + y^2 = r^2\\], then \\(r > 0\\).';
      expect(normalizeMathDelimiters(input)).toBe('Given $a > 0$ and $$x^2 + y^2 = r^2$$, then $r > 0$.');
    });

    it('drops the padding inside \\( \\) so the closing $ is not refused as a spaced closer', () => {
      expect(normalizeMathDelimiters('so \\( a+b \\) holds')).toBe('so $a+b$ holds');
      expect(parse('so \\( a+b \\) holds').formulas).toEqual(['a+b']);
    });

    it('leaves an empty \\( \\) alone', () => {
      expect(normalizeMathDelimiters('empty \\(  \\) here')).toBe('empty \\(  \\) here');
    });
  });

  describe('code stays untouched', () => {
    it('does not convert inside fenced code blocks', () => {
      const code = '```python\ndata = arr[\\n]\n```';
      expect(normalizeMathDelimiters(`${code}\n\nFormula: \\[x=1\\]`)).toBe(`${code}\n\nFormula: $$x=1$$`);
    });

    it('does not convert inside tilde fences', () => {
      const code = '~~~sh\necho "\\(not math\\)"\n~~~';
      expect(normalizeMathDelimiters(`${code}\n\n\\(x\\)`)).toBe(`${code}\n\n$x$`);
    });

    it('does not convert inside inline code', () => {
      expect(normalizeMathDelimiters('Use `\\(regex\\)` pattern. Also \\(x=1\\).')).toBe(
        'Use `\\(regex\\)` pattern. Also $x=1$.',
      );
    });

    it('does not convert inside an unclosed fence while streaming', () => {
      const input = '```python\nresult = data[\\n]\nprint(result';
      expect(normalizeMathDelimiters(input, true)).toBe(input);
    });

    it('puts code back byte for byte, including $ replacement patterns', () => {
      const fence = '```js\ns.replace(/a/, "$&$$$\'$`");\n```';
      const inline = "`x.replace(/a/, '$&')`";
      const input = `${fence}\n\n${inline} and \\(y\\)`;
      expect(normalizeMathDelimiters(input)).toBe(`${fence}\n\n${inline} and $y$`);
    });

    it('survives text that looks like its own placeholder', () => {
      const input = 'tag MATHCODE0_ and `code` and MATHCODE_1_ then \\(x\\)';
      expect(normalizeMathDelimiters(input)).toBe('tag MATHCODE0_ and `code` and MATHCODE_1_ then $x$');
    });
  });

  describe('streaming', () => {
    it('escapes an unpaired $$', () => {
      const result = normalizeMathDelimiters('The solution is $$\\frac{1}{', true);
      expect(result).toBe('The solution is \\$\\$\\frac{1}{');
    });

    it('escapes only the last unpaired $$', () => {
      expect(normalizeMathDelimiters('$$a$$ and $$b', true)).toBe('$$a$$ and \\$\\$b');
    });

    it('leaves paired $$ alone', () => {
      expect(normalizeMathDelimiters('Formula $$x = 1$$ done.', true)).toBe('Formula $$x = 1$$ done.');
    });

    it('does not count a $$ inside code', () => {
      const input = 'Run `echo $$` and $$x=1$$ now';
      expect(normalizeMathDelimiters(input, true)).toBe(input);
    });

    it('leaves an unpaired $$ alone once the answer is complete', () => {
      expect(normalizeMathDelimiters('Incomplete $$\\frac{1}{')).toBe('Incomplete $$\\frac{1}{');
    });
  });

  describe('text without work to do', () => {
    it('returns the same text', () => {
      const input = 'Hello world. This is a normal paragraph with a price of $5.';
      expect(normalizeMathDelimiters(input)).toBe(input);
    });

    it('keeps existing delimiters', () => {
      expect(normalizeMathDelimiters('Already correct: $$E = mc^2$$ and $x$')).toBe(
        'Already correct: $$E = mc^2$$ and $x$',
      );
    });

    it('handles empty content', () => {
      expect(normalizeMathDelimiters('')).toBe('');
      expect(normalizeMathDelimiters('', true)).toBe('');
    });
  });
});

type LiteralCase = [name: string, markdown: string, formulaCount: number, literals: string[]];

/** Text where a `$` is money, a variable or code: it must stay as written, and real formulas next to it still count. */
const LITERAL_CASES: LiteralCase[] = [
  ['bold prices', 'The **Pro** plan is **$20/month** and **Team** is **$30/month**.', 0, ['$20/month', '$30/month']],
  ['strike price', 'Was ~~$99~~ now $49, saving $50.', 0, ['$99', '$49', '$50']],
  ['heading with prices', '## From $5 to $10 per seat', 0, ['$5 to $10']],
  ['blockquote prices', '> Costs $5 now and $10 later.', 0, ['$5 now and $10']],
  [
    'numbered list bold prices',
    '1. **Pro** — $20/month ($200/year)\n2. **Max** — $100/month ($1,000/year)',
    0,
    ['$20/month ($200/year)', '$100/month ($1,000/year)'],
  ],
  ['table row prices', '| Plan | Price |\n|---|---|\n| Pro | $20 |\n| Max | $100 |', 0, ['$20', '$100']],
  ['link text with prices', 'See [plans from $5 to $10](https://example.com/pricing) for details.', 0, ['$5 to $10']],
  ['currency then real formula', 'It costs $5 and the area is $\\pi r^2$ here.', 1, ['$5 and the area is']],
  ['real formula then currency', 'The area is $\\pi r^2$ and it costs $5 and $7.', 1, ['$5 and $7']],
  [
    'display math between prices',
    'Prices $5 and $10.\n\n$$E = mc^2$$\n\nThen $20 more.',
    1,
    ['$5 and $10', '$20 more'],
  ],
  ['mixed escaped and bare', 'Costs \\$5 and $10 and $20 each.', 0, ['$5 and $10 and $20']],
  ['zh prices', '版本A售价$5，版本B售价$10，差价$5。', 0, ['$5，版本B售价$10，差价$5']],
  ['zh finance with formulas', '存入$1,000，利率$r$，$n$年后得到$1000(1+r)^n$。', 3, ['$1,000']],
  [
    'bare url with $digit',
    'See https://example.com/a$1b$2 for $5 and $10.',
    0,
    ['https://example.com/a$1b$2', '$5 and $10'],
  ],
  ['www url with $digit', 'Visit www.example.com/p$1/q$2 for $5 and $10.', 0, ['$5 and $10']],
  ['angle autolink with $digit', 'Open <https://example.com/a$1b$2> for $5 and $10.', 0, ['$5 and $10']],
  [
    'indented code then prices',
    "Run:\n\n    awk '{print $1, $2}'\n\nthen pay $5 and $10",
    0,
    ['{print $1, $2}', '$5 and $10'],
  ],
  ['tilde fence then prices', '~~~\necho $5 $6\n~~~\n\ncosts $5 and $10', 0, ['echo $5 $6', '$5 and $10']],
  ['inline code then prices', 'Run `echo $5 $6` then pay **$10** and $20.', 0, ['echo $5 $6', '$10', '$20']],
  [
    'list continuation with formula',
    '1. Step one\n\n    The cost is $5 and $x^2$ holds.\n\n2. Step two',
    1,
    ['$5 and'],
  ],
  ['two formulas', 'We have $a+b$ and $c+d$.', 2, []],
  ['one price only', 'Only $5.', 0, ['$5']],
  ['non-USD symbols', 'Costs €5 and £10 and ¥1000.', 0, ['€5 and £10 and ¥1000']],
  [
    'shell variable then inline code',
    'Use $HOME, then run `echo $HOME` and `cd $DIR`.',
    0,
    ['$HOME, then run', 'echo $HOME', 'cd $DIR'],
  ],
  [
    'json schema ref then code',
    'The $ref key resolves via `flatten($ref)` before `$defs` is dropped.',
    0,
    ['$ref key resolves via', 'flatten($ref)', '$defs'],
  ],
  ['shell variables in prose', 'Set $JAVA_HOME and $PATH before running.', 0, ['$JAVA_HOME and $PATH']],
  ['env variable list in prose', 'Variables like $USER, $HOME are expanded.', 0, ['$USER, $HOME']],
  ['schema keys in prose', 'Use $ref for the schema and $defs for definitions.', 0, ['$ref for the schema and $defs']],
  ['brace and arithmetic expansion in prose', 'Both ${VAR} and $((1+2)) are expanded.', 0, ['${VAR} and $((1+2))']],
  ['formula then inline code', 'Let $x^2$ be the cost and run `f(x)` after.', 1, ['f(x)']],
  ['formula between two code spans', 'Run `a` then $y_i$ then `b $c`.', 1, ['a', 'b $c']],
];

type FormulaCase = [name: string, markdown: string, formulas: string[]];

/** Where exactly the parser draws the line between a formula and a dollar sign. */
const FORMULA_CASES: FormulaCase[] = [
  ['display math is untouched', '$$\nE = mc^2\n$$', ['E = mc^2']],
  ['inline $$ followed by a digit stays math', 'See $$x$$5 here', ['x']],
  ['escaped dollars', 'Costs \\$5 and \\$10.', []],
  ['digit-led real formulas', 'Solve $2x+3$ and $10^{-3}$ now', ['2x+3', '10^{-3}']],
  ['bare number formula', 'There are $3$ items', ['3']],
  ['closer followed by a digit', 'x$3$4', []],
  ['two prices', 'costs $5 and $10 each', []],
  ['price range', 'from $5-$10', []],
  ['US-prefixed prices', 'US$5 and US$10', []],
  ['price then formula', 'between $5 and $x$', ['x']],
  ['price comma formula', 'costs $5, $x$', ['x']],
  ['CJK prices', '版本A售价$5，版本B售价$10，差价$5。', []],
  ['CJK finance with formulas', '存入$1,000，利率$r$，$n$年后得到$1000(1+r)^n$。', ['r', 'n', '1000(1+r)^n']],
  ['CJK after a formula', '设$x$的值为$2x$个', ['x', '2x']],
  ['spaced non-digit formula stays math', 'we have $ x^2 $ here', ['x^2']],
  ['digit-led closer preceded by a space', 'total $5 + 3 $ ok', []],
  ['table prices', '| a | b |\n|---|---|\n| $5 | $10 |', []],
  ['shell variable then inline code', 'Use $HOME, then run `echo $HOME`.', []],
  ['json ref then inline code', 'The $ref key and `flatten($ref)` and `$defs`.', []],
  ['unquoted shell variables', 'Set $JAVA_HOME and $PATH before running.', []],
  ['tight opener with spaced closer is not math', 'Then $a+b $ holds.', []],
  ['tight formulas', 'Let $x$ and $y$ be reals, then $x+y$ holds.', ['x', 'y', 'x+y']],
  ['formula between code spans', 'Run `a` then $y_i$ then `b $c`.', ['y_i']],
  ['backtick inside a span is not math', 'weird $a `b` c$ text', []],
  ['inline code first', 'Run `echo $5 $6` and pay $10 now', []],
  ['url with dollar digits', 'See https://e.com/a$1b$2 and $x$.', ['x']],
  ['multiline paragraph prices', 'costs $5\nand $10 later', []],
  ['multiline formula', 'let $a +\nb$ be', ['a +\nb']],
];

describe('math parsing policy', () => {
  it.each(LITERAL_CASES)('%s', (_name, markdown, formulaCount, literals) => {
    const { formulas, text } = parse(markdown);
    expect(formulas).toHaveLength(formulaCount);
    for (const literal of literals) {
      expect(text).toContain(literal);
    }
  });

  it.each(FORMULA_CASES)('%s', (_name, markdown, expected) => {
    expect(parse(markdown).formulas).toEqual(expected);
  });
});

describe('math rendering', () => {
  it('renders inline and display formulas with KaTeX, whichever delimiters the model used', () => {
    expect(render('so $x^2$ holds')).toContain('class="katex"');
    expect(render('so \\(x^2\\) holds')).toContain('class="katex"');
    expect(render('$$\nx^2\n$$')).toContain('katex-display');
    expect(render('\\[x^2\\]')).toContain('class="katex"');
  });

  it('keeps the rest of a formula after a percent sign', () => {
    const html = render('$$50% \\text{done}$$');
    expect(html).toContain('done');
    expect(html).not.toContain('katex-error');
  });

  it('leaves the percent signs of prose and code alone', () => {
    const html = render('Costs $5 and later $10, up 100% overall.\n\n`50%`\n\n```\n100%\n```');
    expect(html).toContain('up 100% overall');
    expect(html).toContain('<code>50%</code>');
    expect(html).toContain('<code>100%\n</code>');
    expect(html).not.toContain('\\%');
  });

  it('renders Chinese text inside a formula', () => {
    const html = render('$$\\text{面积} = \\pi r^2$$');
    expect(html).toContain('面积');
    expect(html).not.toContain('katex-error');
  });

  it('degrades invalid TeX to KaTeX error markup instead of throwing', () => {
    expect(render('broken $\\frac{1}{$ here')).toContain('katex-error');
  });
});

describe('KaTeX options per preset', () => {
  it('keeps commands that link or load a resource switched off outside the chat', () => {
    const html = render('$\\href{https://example.com}{x}$ and $\\includegraphics{https://example.com/a.png}$');
    expect(html).toContain('class="katex"');
    expect(html).not.toContain('<a ');
    expect(html).not.toContain('<img');
  });

  it('lets chat messages use them', () => {
    expect(renderChat('$\\href{https://example.com}{x}$')).toContain('href="https://example.com"');
  });

  it('gives chat messages html-only output and the other surfaces MathML next to it', () => {
    expect(renderChat('$x$')).not.toContain('katex-mathml');
    expect(render('$x$')).toContain('katex-mathml');
  });

  it('runs the same parser policy and percent escape in both', () => {
    for (const run of [render, renderChat]) {
      expect(run('Costs $5 and $10 and $$50% \\text{done}$$')).not.toContain('katex-error');
      expect(run('Costs $5 and $10')).not.toContain('class="katex"');
    }
  });
});

/** The chat order: the raw HTML of a message becomes elements first, then the chat math list runs on that tree. */
const rawChatRenderer = unified()
  .use(remarkParse)
  .use(remarkGfm)
  .use(chatMathPlugins.remark)
  .use(remarkRehype, { allowDangerousHtml: true })
  .use(rehypeRaw)
  .use(chatMathPlugins.rehype)
  .use(rehypeStringify);
const renderChatRaw = (markdown: string): string =>
  String(rawChatRenderer.processSync(normalizeMathDelimiters(markdown)));
const countOf = (html: string, tag: string): number => html.split(`<${tag}`).length - 1;

describe('SVG in chat messages', () => {
  it('unwraps the vector markup a message carries and keeps what is inside it', () => {
    const html = renderChatRaw('a <svg viewBox="0 0 4 4"><path d="M0 0"></path><line x1="0"></line>kept</svg> b');
    for (const tag of ['svg', 'path', 'line']) {
      expect(countOf(html, tag)).toBe(0);
    }
    expect(html).toContain('a kept b');
  });

  it('unwraps vector tags nested in vector tags', () => {
    const html = renderChatRaw('<svg><svg><path d="M0 0"></path>deep</svg></svg>');
    expect(countOf(html, 'svg') + countOf(html, 'path')).toBe(0);
    expect(html).toContain('deep');
  });

  it('keeps the SVG KaTeX draws for roots and vectors', () => {
    const html = renderChatRaw('$\\sqrt{x}$ and $\\vec{v}$');
    expect(countOf(html, 'svg')).toBeGreaterThan(0);
    expect(countOf(html, 'path')).toBeGreaterThan(0);
  });

  it('leaves no SVG behind a forged formula wrapper except what KaTeX draws itself', () => {
    const forged = '<span class="katex"><svg><path d="M0 0"></path></svg></span>';
    expect(countOf(renderChatRaw(`${forged} $\\sqrt{x}$`), 'svg')).toBe(countOf(renderChatRaw('$\\sqrt{x}$'), 'svg'));
  });
});
