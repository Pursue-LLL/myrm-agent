import { describe, it, expect } from 'vitest';
import { preprocessContentMath, escapeIncompleteBlockMath } from '../MathRenderer';

describe('preprocessContentMath', () => {
  describe('LaTeX delimiter conversion', () => {
    it('converts \\[...\\] to $$...$$', () => {
      const input = 'The answer is \\[x = \\frac{-b}{2a}\\] done.';
      const result = preprocessContentMath(input);
      expect(result).toContain('$$x = \\frac{-b}{2a}$$');
      expect(result).not.toContain('\\[');
      expect(result).not.toContain('\\]');
    });

    it('converts \\(...\\) to $...$', () => {
      const input = 'Inline formula \\(E = mc^2\\) here.';
      const result = preprocessContentMath(input);
      expect(result).toContain('$E = mc^2$');
      expect(result).not.toContain('\\(');
      expect(result).not.toContain('\\)');
    });

    it('handles multiline \\[...\\]', () => {
      const input = '\\[\n\\begin{aligned}\nx &= 1 \\\\\ny &= 2\n\\end{aligned}\n\\]';
      const result = preprocessContentMath(input);
      expect(result).toContain('$$\n\\begin{aligned}');
      expect(result).toContain('\\end{aligned}\n$$');
    });

    it('handles multiple conversions in one text', () => {
      const input = 'Given \\(a > 0\\) and \\[x^2 + y^2 = r^2\\], then \\(r > 0\\).';
      const result = preprocessContentMath(input);
      expect(result).toContain('$a > 0$');
      expect(result).toContain('$$x^2 + y^2 = r^2$$');
      expect(result).toContain('$r > 0$');
    });
  });

  describe('code block protection', () => {
    it('does not convert \\[ inside fenced code blocks', () => {
      const input = '```python\ndata = arr[\\n]\n```\n\nFormula: \\[x=1\\]';
      const result = preprocessContentMath(input);
      expect(result).toContain('```python\ndata = arr[\\n]\n```');
      expect(result).toContain('$$x=1$$');
    });

    it('does not convert \\( inside inline code', () => {
      const input = 'Use `\\(regex\\)` pattern. Also \\(x=1\\).';
      const result = preprocessContentMath(input);
      expect(result).toContain('`\\(regex\\)`');
      expect(result).toContain('$x=1$');
    });

    it('handles unclosed fenced code block (streaming)', () => {
      const input = '```python\nresult = data[\\n]\nprint(result';
      const result = preprocessContentMath(input);
      // Should not convert anything inside the unclosed code block
      expect(result).toContain('data[\\n]');
      expect(result).not.toContain('$$');
    });
  });

  describe('math content preprocessing', () => {
    it('escapes % inside math delimiters', () => {
      const input = '\\[50% \\text{done}\\]';
      const result = preprocessContentMath(input);
      expect(result).toContain('50\\%');
    });

    it('converts Chinese \\text to \\mathrm', () => {
      const input = '\\[\\text{面积} = \\pi r^2\\]';
      const result = preprocessContentMath(input);
      expect(result).toContain('\\mathrm{面积}');
    });
  });

  describe('streaming incomplete protection', () => {
    it('escapes unpaired $$ when streaming', () => {
      const input = 'The solution is $$\\frac{1}{';
      const result = preprocessContentMath(input, true);
      expect(result).not.toMatch(/(?<!\\)\$\$/);
    });

    it('does not escape paired $$ when streaming', () => {
      const input = 'Formula $$x = 1$$ done.';
      const result = preprocessContentMath(input, true);
      expect(result).toContain('$$x = 1$$');
    });

    it('does nothing special when not streaming', () => {
      const input = 'Incomplete $$\\frac{1}{';
      const result = preprocessContentMath(input, false);
      expect(result).toContain('$$\\frac{1}{');
    });
  });

  describe('no false positives', () => {
    it('does not affect normal text without LaTeX', () => {
      const input = 'Hello world. This is a normal paragraph.';
      const result = preprocessContentMath(input);
      expect(result).toBe(input);
    });

    it('preserves existing $$ delimiters', () => {
      const input = 'Already correct: $$E = mc^2$$';
      const result = preprocessContentMath(input);
      expect(result).toContain('$$E = mc^2$$');
    });

    it('handles empty content', () => {
      expect(preprocessContentMath('')).toBe('');
    });
  });
});

describe('escapeIncompleteBlockMath', () => {
  it('escapes single unpaired $$', () => {
    const input = 'Start $$\\frac{1}{2';
    const result = escapeIncompleteBlockMath(input);
    expect(result).toContain('\\$\\$');
    expect(result).not.toMatch(/(?<!\\)\$\$/);
  });

  it('does not escape when all $$ are paired', () => {
    const input = '$$x=1$$ and $$y=2$$';
    const result = escapeIncompleteBlockMath(input);
    expect(result).toBe(input);
  });

  it('handles text with no $$', () => {
    const input = 'No math here';
    const result = escapeIncompleteBlockMath(input);
    expect(result).toBe(input);
  });
});
