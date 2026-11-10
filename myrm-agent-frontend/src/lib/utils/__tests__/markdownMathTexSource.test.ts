import rehypeStringify from 'rehype-stringify';
import remarkGfm from 'remark-gfm';
import remarkParse from 'remark-parse';
import remarkRehype from 'remark-rehype';
import { unified } from 'unified';
import { describe, expect, it } from 'vitest';
import { mathPlugins, normalizeMathDelimiters, texSourceMathPlugins } from '../markdownMath';

type Preset = typeof mathPlugins;

const rendererFor = (preset: Preset) =>
  unified()
    .use(remarkParse)
    .use(remarkGfm)
    .use(preset.remark)
    .use(remarkRehype)
    .use(preset.rehype)
    .use(rehypeStringify);
const texRenderer = rendererFor(texSourceMathPlugins);
const katexRenderer = rendererFor(mathPlugins);
const render = (markdown: string): string => String(texRenderer.processSync(normalizeMathDelimiters(markdown)));
const renderKatex = (markdown: string): string => String(katexRenderer.processSync(normalizeMathDelimiters(markdown)));
const count = (text: string, pattern: RegExp): number => (text.match(pattern) ?? []).length;

describe('texSourceMathPlugins', () => {
  it('keeps an inline formula as its TeX source between dollar signs', () => {
    expect(render('so $x^2$ holds')).toBe('<p>so $x^2$ holds</p>');
    expect(render('so \\(x^2\\) holds')).toBe('<p>so $x^2$ holds</p>');
  });

  it('keeps a display formula as one paragraph between double dollar signs', () => {
    expect(render('$$\ne^{i\\pi}=-1\n$$')).toBe('<p>$$e^{i\\pi}=-1$$</p>');
    expect(render('\\[\nx^2\n\\]')).toBe('<p>$$x^2$$</p>');
  });

  it('treats a math code fence like a display formula, without the fence’s trailing newline', () => {
    expect(render('```math\nx^2\n```')).toBe('<p>$$x^2$$</p>');
  });

  it('keeps formulas inside lists, quotes and tables', () => {
    const html = render('- item $a$\n\n> quote $b$\n\n| h |\n| - |\n| $c$ |');

    for (const source of ['$a$', '$b$', '$c$']) {
      expect(html).toContain(source);
    }
  });

  it('keeps the source as typed, percent signs included', () => {
    const html = render('$$50% \\text{done}$$');

    expect(html).toContain('50% \\text{done}');
    expect(html).not.toContain('\\%');
  });

  it('escapes the characters of the source that are markup in HTML', () => {
    expect(render('$a<b$')).toBe('<p>$a&#x3C;b$</p>');
  });

  it('decides what is a formula the way the other presets do', () => {
    expect(render('Costs $5 and $10 a month.')).toBe('<p>Costs $5 and $10 a month.</p>');
    expect(render('Run `echo $HOME` now')).toBe('<p>Run <code>echo $HOME</code> now</p>');
  });

  it('writes no KaTeX markup', () => {
    const html = render('Inline $a+b$ and\n\n$$\n\\frac{1}{2}\n$$');

    expect(html).not.toMatch(/katex|<math|annotation|<span/);
  });

  it.each([
    ['inline dollars', 'so $x^2$ holds'],
    ['inline parentheses', 'so \\(x^2\\) holds'],
    ['bracketed on one line', '\\[x^2\\]'],
    ['bracketed on several lines', '\\[\nx^2\n\\]'],
    ['display dollars', '$$\ne^{i\\pi}=-1\n$$'],
    ['math fence', '```math\nx^2\n```'],
    ['display in a list', '- item\n\n  $$\n  y\n  $$'],
    ['display in a quote', '> $$\n> z\n> $$'],
    ['several formulas', 'a $b$ and\n\n$$\nc\n$$\n\nthen $d$'],
  ])('finds the same inline and display formulas as the KaTeX preset: %s', (_label, markdown) => {
    const katex = renderKatex(markdown);
    const displays = count(katex, /katex-display/g);

    // Every formula has two delimiters: `$$ … $$` for a display one, `$ … $` for an inline one.
    expect({
      display: count(render(markdown), /\$\$/g) / 2,
      inline: count(render(markdown), /(?<!\$)\$(?!\$)/g) / 2,
    }).toEqual({ display: displays, inline: count(katex, /class="katex"/g) - displays });
  });
});
