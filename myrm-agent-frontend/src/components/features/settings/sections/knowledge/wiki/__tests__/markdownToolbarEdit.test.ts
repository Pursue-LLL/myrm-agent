import { describe, expect, it } from 'vitest';

import { buildToolbarEdit, type MarkdownSnippetCopy } from '../markdownToolbarEdit';

const copy: MarkdownSnippetCopy = {
  bold: 'bold text',
  italic: 'italic text',
  heading: 'Heading',
  code: 'code',
  quote: 'Quoted text',
  bullet: 'List item',
  todo: 'To-do',
  wikilink: 'Page name',
  tableHeader: (index) => `Header ${index}`,
  tableCell: (index) => `Content ${index}`,
};

describe('buildToolbarEdit', () => {
  it('wraps the selection without selecting anything afterwards', () => {
    expect(buildToolbarEdit('bold', 'hello', copy)).toEqual({ text: '**hello**' });
    expect(buildToolbarEdit('italic', 'hello', copy)).toEqual({ text: '*hello*' });
    expect(buildToolbarEdit('wikilink', 'Home', copy)).toEqual({ text: '[[Home]]' });
    expect(buildToolbarEdit('code', 'x = 1', copy)).toEqual({ text: '`x = 1`' });
  });

  it('inserts the placeholder and selects exactly that placeholder', () => {
    expect(buildToolbarEdit('bold', '', copy)).toEqual({
      text: '**bold text**',
      select: { startOffset: 2, length: 'bold text'.length },
    });
    expect(buildToolbarEdit('wikilink', '', copy)).toEqual({
      text: '[[Page name]]',
      select: { startOffset: 2, length: 'Page name'.length },
    });
  });

  it('measures the selected span from the placeholder of any language', () => {
    const zh = { ...copy, italic: '斜体文本', code: '代码' };

    expect(buildToolbarEdit('italic', '', zh).select).toEqual({ startOffset: 1, length: 4 });
    expect(buildToolbarEdit('code', '', zh).select).toEqual({ startOffset: 1, length: 2 });
  });

  it('turns a multi-line code selection into a fenced block', () => {
    expect(buildToolbarEdit('code', 'a\nb', copy)).toEqual({ text: '\n```markdown\na\nb\n```\n' });
  });

  it('prefixes block actions with the selection or the placeholder', () => {
    expect(buildToolbarEdit('h2', 'Title', copy).text).toBe('\n## Title\n');
    expect(buildToolbarEdit('h2', '', copy).text).toBe('\n## Heading\n');
    expect(buildToolbarEdit('quote', '', copy).text).toBe('\n> Quoted text\n');
    expect(buildToolbarEdit('bullet', 'one', copy).text).toBe('\n- one\n');
    expect(buildToolbarEdit('todo', '', copy).text).toBe('\n- [ ] To-do\n');
  });

  it('builds a two-column table from the numbered header and cell copy', () => {
    expect(buildToolbarEdit('table', '', copy).text).toBe(
      '\n| Header 1 | Header 2 |\n| --- | --- |\n| Content 1 | Content 2 |\n',
    );
  });
});
