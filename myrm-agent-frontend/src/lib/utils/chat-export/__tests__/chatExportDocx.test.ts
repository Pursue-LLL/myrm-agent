/** @vitest-environment jsdom */
import { describe, expect, it } from 'vitest';
import { buildDocxBlob } from '../chatExportDocx';
import {
  elements,
  externalTargets,
  hasIllegalXmlChar,
  openDocx,
  paragraphTexts,
  parseXml,
  wordText,
  type DocxPackage,
} from './docxTestKit';

const docxOf = async (markdown: string): Promise<DocxPackage> => openDocx(await buildDocxBlob(markdown));
const attr = (node: Element, name = 'w:val'): string | null => node.getAttribute(name);
const styleIds = (docx: DocxPackage): Array<string | null> => elements(docx.document, 'w:pStyle').map((s) => attr(s));
const textOf = (docx: DocxPackage): string => paragraphTexts(docx.document).join('\n');

/** The list each paragraph belongs to and its level, for the paragraphs that sit in a list. */
function listItems(docx: DocxPackage): Array<{ text: string; numId: string | null; level: string | null }> {
  return elements(docx.document, 'w:p')
    .filter((p) => elements(p, 'w:numPr').length > 0)
    .map((p) => ({
      text: wordText(p),
      numId: attr(elements(p, 'w:numId')[0]),
      level: attr(elements(p, 'w:ilvl')[0]),
    }));
}

describe('Word file structure', () => {
  it('writes headings as Word heading styles', async () => {
    const docx = await docxOf('# Title\n\n## Part\n\nBody text.');

    expect(styleIds(docx)).toEqual(expect.arrayContaining(['Heading1', 'Heading2']));
    expect(paragraphTexts(docx.document)).toEqual(['Title', 'Part', 'Body text.']);
  });

  it('keeps every list item, its nesting and its order', async () => {
    const items = listItems(await docxOf('- a\n- b\n  - c\n- d\n\n1. one\n2. two'));

    expect(items.map(({ text }) => text)).toEqual(['a', 'b', 'c', 'd', 'one', 'two']);
    expect(items.map(({ level }) => level)).toEqual(['0', '0', '1', '0', '0', '0']);
    expect(items[0].numId).not.toBe(items[4].numId);
  });

  it('numbers each ordered list from 1 and does not carry on from the list before', async () => {
    const items = listItems(await docxOf('1. a\n2. b\n\nBetween.\n\n1. c\n2. d'));

    expect(items[0].numId).toBe(items[1].numId);
    expect(items[2].numId).toBe(items[3].numId);
    expect(items[0].numId).not.toBe(items[2].numId);
  });

  it('writes a table as a Word table with its cells, a bold header and its alignment', async () => {
    const docx = await docxOf('| Name | Score |\n|:--|--:|\n| **Ann** | 9 |\n| Bob | 7 |');
    const [table] = elements(docx.document, 'w:tbl');
    const rows = elements(table, 'w:tr');

    expect(rows).toHaveLength(3);
    expect(elements(table, 'w:tc').map((cell) => paragraphTexts(cell).join(''))).toEqual([
      'Name',
      'Score',
      'Ann',
      '9',
      'Bob',
      '7',
    ]);
    expect(elements(rows[0], 'w:b').length).toBeGreaterThan(0);
    expect(elements(rows[2], 'w:b')).toHaveLength(0);
    expect(elements(rows[1], 'w:jc').map((jc) => attr(jc))).toEqual(['left', 'right']);
  });

  it('keeps a line break inside a table cell and inside a paragraph, and drops a lone <br> line', async () => {
    const docx = await docxOf('| a |\n|---|\n| first<br>second |\n\nline one  \nline two\n\n<br>');

    expect(paragraphTexts(docx.document)).toEqual(expect.arrayContaining(['first\nsecond', 'line one\nline two']));
    expect(textOf(docx)).not.toContain('<br');
  });

  it('writes code with the code styles that the file defines', async () => {
    const docx = await docxOf('```ts\nconst a = 1;\nconst b = 2;\n```\n\nUse `inline` here.');
    const styles = docx.parts['word/styles.xml'];

    expect(styleIds(docx)).toContain('CodeBlock');
    expect(textOf(docx)).toContain('const a = 1;');
    expect(textOf(docx)).toContain('const b = 2;');
    expect(elements(docx.document, 'w:rStyle').map((s) => attr(s))).toContain('InlineCode');
    // The converter names these two styles, and Word ignores a name the file does not define.
    expect(styles).toContain('w:styleId="CodeBlock"');
    expect(styles).toContain('w:styleId="InlineCode"');
  });

  it('writes a task list as checkboxes, checked where the item is done', async () => {
    const docx = await docxOf('- [x] done\n- [ ] open\n- plain');

    expect(elements(docx.document, 'w14:checkbox')).toHaveLength(2);
    expect(elements(docx.document, 'w14:checked').map((c) => attr(c, 'w14:val'))).toEqual(['1', '0']);
    expect(textOf(docx)).toMatch(/done[\s\S]*open[\s\S]*plain/);
  });

  it('writes a footnote as a Word footnote, without the page markup around it', async () => {
    const docx = await docxOf('Claim[^1] and another[^2].\n\n[^1]: First note.\n[^2]: Second note.');
    const notes = paragraphTexts(parseXml(docx.parts['word/footnotes.xml'])).join('|');

    expect(elements(docx.document, 'w:footnoteReference')).toHaveLength(2);
    expect(notes).toContain('First note.');
    expect(notes).toContain('Second note.');
    expect(textOf(docx)).not.toContain('Footnotes');
    expect(`${docx.parts['word/document.xml']}${docx.parts['word/footnotes.xml']}`).not.toContain('↩');
  });

  it('writes a rule as a bordered paragraph and keeps a quote', async () => {
    const docx = await docxOf('above\n\n---\n\n> quoted words');

    expect(elements(docx.document, 'w:pBdr').length).toBeGreaterThan(0);
    expect(textOf(docx)).toContain('quoted words');
  });

  it('keeps Chinese, Japanese and right-to-left text as it is', async () => {
    const text = textOf(await docxOf('中文段落，日本語のテキスト。\n\nمرحبا بالعالم שלום עולם'));

    expect(text).toContain('中文段落，日本語のテキスト。');
    expect(text).toContain('مرحبا بالعالم שלום עולם');
  });

  it('writes a valid file with no text when the message is empty', async () => {
    expect(paragraphTexts((await docxOf('')).document).join('')).toBe('');
  });
});

describe('Word file formulas', () => {
  const MARKDOWN = [
    'Energy is $E = mc^2$ and \\(x_1 + x_2\\), but $5 and $10 are prices.',
    '',
    '$$',
    '\\int_0^1 x^2\\,dx = \\frac{1}{3}',
    '$$',
    '',
    '```bash',
    'echo "$HOME"',
    '```',
  ].join('\n');

  it('writes each formula once, as a Word equation, and leaves prices and code alone', async () => {
    const docx = await docxOf(MARKDOWN);
    const text = textOf(docx);

    expect(elements(docx.document, 'm:oMath')).toHaveLength(3);
    expect(text).toContain('but $5 and $10 are prices.');
    expect(text).toContain('echo "$HOME"');
    // The TeX source, or KaTeX's second (visual) half, would show as text if either got through.
    for (const leaked of ['mc^2', 'x_1', '\\int', '\\frac', '$E']) {
      expect(text).not.toContain(leaked);
    }
  });

  it('keeps the source of a formula that KaTeX rejects, as the plain text of the equation, and still writes the file', async () => {
    const docx = await docxOf('Broken: $\\undefinedcommand$ done.');

    expect(elements(docx.document, 'm:t').map((run) => run.textContent)).toEqual(['\\undefinedcommand']);
    expect(textOf(docx)).toBe('Broken:  done.');
  });
});

describe('Word file links', () => {
  const MARKDOWN = [
    '[web](https://a.example/p?q=1) [mail](mailto:x@y.example) [phone](tel:+15551234)',
    '<https://auto.example/page> https://bare.example/z',
    '[rel](/docs/a) [frag](#top) [net](//evil.example/x) [js](javascript:alert(1))',
    '[data](data:text/html;base64,PHNjcmlwdD4=) [cr](java%0Ascript:alert(1)) [ftp](ftp://f.example/x)',
    '[nohost](https://) [badhost](http://[::1)',
  ].join('\n');

  it('keeps links that work outside the page and shows every other link as its text', async () => {
    const docx = await docxOf(MARKDOWN);
    const targets = externalTargets(docx.parts['word/_rels/document.xml.rels']);

    expect([...targets].sort()).toEqual([
      'https://a.example/p?q=1',
      'https://auto.example/page',
      'https://bare.example/z',
      'mailto:x@y.example',
      'tel:+15551234',
    ]);
    expect(elements(docx.document, 'w:hyperlink')).toHaveLength(5);
    for (const shown of ['rel', 'frag', 'net', 'js', 'data', 'cr', 'ftp', 'nohost', 'badhost']) {
      expect(textOf(docx)).toContain(shown);
    }
  });

  it('drops raw HTML, so no script or tag text reaches the file', async () => {
    const text = textOf(
      await docxOf('<script>alert(1)</script>\n\nSome <b>bold</b> words and <img src=x onerror=alert(2)>.'),
    );

    expect(text).toContain('Some bold words and .');
    expect(text).not.toMatch(/alert|<script|<b>|onerror/);
  });
});

describe('Word file robustness', () => {
  it('writes only characters XML allows, whatever the message holds', async () => {
    const docx = await docxOf(
      `before \uFFFE \uFFFF \u0000 \u0001 \u000B \uD800 \uDC00 after\n\n\`\`\`\ncode \uFFFE \u0001 end\n\`\`\``,
    );

    expect(hasIllegalXmlChar(Object.values(docx.parts).join(''))).toBe(false);
    expect(textOf(docx)).toMatch(/before[\s\S]*after[\s\S]*end/);
  });

  it('proves the kit refuses what a strict reader would refuse', () => {
    expect(() => parseXml('<a>\uFFFE</a>')).toThrow('Not well-formed XML');
    expect(() => parseXml('<a><b></a>')).toThrow('Not well-formed XML');
    for (const bad of [
      '\uFFFE',
      '\uFFFF',
      '\u0000',
      '\u0001',
      '\u000B',
      '\uD800',
      '\uDC00',
      'a\uD800b',
      '\uDC00\uD800',
    ]) {
      expect(hasIllegalXmlChar(bad)).toBe(true);
    }
    expect(hasIllegalXmlChar('ok \uD83D\uDE00 \t\n\r 中文')).toBe(false);
  });

  it('names Myrm as the author of the file', async () => {
    const core = (await docxOf('text')).parts['docProps/core.xml'];

    expect(core).toContain('<dc:creator>Myrm</dc:creator>');
    expect(core).toContain('<cp:lastModifiedBy>Myrm</cp:lastModifiedBy>');
  });
});
