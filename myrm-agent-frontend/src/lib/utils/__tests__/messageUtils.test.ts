import { stripDatetimeTag, stripMarkdown, getBrowserTimezone } from '../messageUtils';

describe('stripDatetimeTag', () => {
  it('removes current_datetime tags', () => {
    const input = '<current_datetime>2026-05-27T14:00:00Z</current_datetime>Hello world';
    expect(stripDatetimeTag(input)).toBe('Hello world');
  });

  it('handles text without tags', () => {
    expect(stripDatetimeTag('plain text')).toBe('plain text');
  });

  it('handles empty string', () => {
    expect(stripDatetimeTag('')).toBe('');
  });

  it('removes multiple tags', () => {
    const input = '<current_datetime>t1</current_datetime>A<current_datetime>t2</current_datetime>B';
    expect(stripDatetimeTag(input)).toBe('AB');
  });
});

describe('stripMarkdown', () => {
  it('removes inline code', () => {
    expect(stripMarkdown('fix `utils.ts` bug')).toBe('fix  bug');
  });

  it('removes code blocks', () => {
    const md = 'before\n```ts\nconst x = 1;\n```\nafter';
    expect(stripMarkdown(md)).toBe('before\nafter');
  });

  it('removes bold and italic markers', () => {
    expect(stripMarkdown('use **bold** and *italic*')).toBe('use bold and italic');
  });

  it('converts links to text', () => {
    expect(stripMarkdown('see [docs](https://example.com)')).toBe('see docs');
  });

  it('removes image syntax', () => {
    expect(stripMarkdown('![alt](image.png) text')).toBe('text');
  });

  it('removes heading markers', () => {
    expect(stripMarkdown('## Title\ncontent')).toBe('Title\ncontent');
  });

  it('removes thinking/reasoning blocks', () => {
    const md = '<think>internal reasoning</think>visible text';
    expect(stripMarkdown(md)).toBe('visible text');
  });

  it('removes REASONING_SCRATCHPAD blocks', () => {
    const md = '<REASONING_SCRATCHPAD>thinking</REASONING_SCRATCHPAD>result';
    expect(stripMarkdown(md)).toBe('result');
  });

  it('removes citation tags', () => {
    expect(stripMarkdown('text<citation id="1"></citation> more')).toBe('text more');
  });

  it('removes blockquote markers', () => {
    expect(stripMarkdown('> quoted text')).toBe('quoted text');
  });

  it('removes list markers', () => {
    expect(stripMarkdown('- item one')).toBe('item one');
    expect(stripMarkdown('* item two')).toBe('item two');
    expect(stripMarkdown('+ item three')).toBe('item three');
  });

  it('removes ordered list markers', () => {
    expect(stripMarkdown('1. first\n2. second')).toBe('first\nsecond');
  });

  it('removes table syntax', () => {
    const md = '| col1 | col2 |\n|---|---|\ntext';
    expect(stripMarkdown(md)).toBe('text');
  });

  it('collapses multiple newlines', () => {
    expect(stripMarkdown('a\n\n\n\nb')).toBe('a\nb');
  });

  it('handles empty string', () => {
    expect(stripMarkdown('')).toBe('');
  });

  it('handles plain text without markdown', () => {
    expect(stripMarkdown('just plain text')).toBe('just plain text');
  });

  it('handles combined markdown and datetime tag cleanup', () => {
    const input = '<current_datetime>2026-05-27</current_datetime>fix `bug` in **module**';
    const cleaned = stripMarkdown(stripDatetimeTag(input));
    expect(cleaned).toBe('fix  in module');
  });
});

describe('getBrowserTimezone', () => {
  it('returns a valid timezone string', () => {
    const tz = getBrowserTimezone();
    expect(typeof tz).toBe('string');
    expect(tz.length).toBeGreaterThan(0);
  });
});
