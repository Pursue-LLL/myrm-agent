/** @vitest-environment jsdom */
import { fireEvent, render, screen } from '@testing-library/react';
import { useState } from 'react';
import { describe, expect, it, vi } from 'vitest';
import { MAX_HIGHLIGHT_LINE_CHARS } from '@/lib/syntax/prism';
import { LineNumberedCode, LineNumberedEditor } from '../WorkspaceTextViews';

const appTheme = vi.hoisted(() => ({ resolved: 'light' }));

vi.mock('next-themes', () => ({
  useTheme: () => ({ resolvedTheme: appTheme.resolved }),
}));

function Editor({ initial }: { initial: string }) {
  const [content, setContent] = useState(initial);
  return <LineNumberedEditor content={content} label="notes.txt" onChange={setContent} />;
}

const gutterOf = (container: HTMLElement): HTMLElement => {
  const gutter = container.querySelector<HTMLElement>('[aria-hidden="true"]');
  if (!gutter) {
    throw new Error('line-number gutter not rendered');
  }
  return gutter;
};

describe('LineNumberedEditor', () => {
  it('numbers every line, the empty one after a final line break included', () => {
    const { container } = render(<Editor initial={'alpha\nbeta\n'} />);
    expect(gutterOf(container).textContent).toBe('1\n2\n3');
  });

  it('numbers a single line and an empty file as line 1', () => {
    const first = render(<Editor initial="alpha" />);
    expect(gutterOf(first.container).textContent).toBe('1');
    first.unmount();

    const second = render(<Editor initial="" />);
    expect(gutterOf(second.container).textContent).toBe('1');
  });

  it('follows the text as lines are added and removed', () => {
    const { container } = render(<Editor initial={'alpha\nbeta'} />);
    const textbox = screen.getByRole('textbox');

    fireEvent.change(textbox, { target: { value: 'alpha\nbeta\ngamma\ndelta' } });
    expect(gutterOf(container).textContent).toBe('1\n2\n3\n4');

    fireEvent.change(textbox, { target: { value: 'alpha' } });
    expect(gutterOf(container).textContent).toBe('1');
  });

  it('keeps the numbers out of the accessibility tree: they only decorate the textbox', () => {
    const { container } = render(<Editor initial={'a\nb\nc'} />);
    expect(gutterOf(container).getAttribute('aria-hidden')).toBe('true');
    expect(screen.getByRole('textbox')).toBeTruthy();
  });

  it('names the textbox after the file, so a screen reader says which file is being edited', () => {
    render(<Editor initial="alpha" />);
    expect(screen.getByRole('textbox', { name: 'notes.txt' })).toBeTruthy();
  });

  it('scrolls the numbers together with the text', () => {
    const { container } = render(<Editor initial={'a\nb\nc'} />);
    const textbox = screen.getByRole('textbox');

    textbox.scrollTop = 120;
    fireEvent.scroll(textbox);

    expect(gutterOf(container).scrollTop).toBe(120);
  });
});

const rowsOf = (container: HTMLElement): HTMLElement[] =>
  Array.from(container.querySelectorAll<HTMLElement>('.numbered-code-line'));

describe('LineNumberedCode', () => {
  it('renders one row per line, and copying the rows gives the file back byte for byte', () => {
    const withFinalBreak = render(<LineNumberedCode content={'one\n\n  two\t \nthree\n'} />);
    expect(rowsOf(withFinalBreak.container)).toHaveLength(4);
    expect(withFinalBreak.container.textContent).toBe('one\n\n  two\t \nthree\n');
    withFinalBreak.unmount();

    const withoutFinalBreak = render(<LineNumberedCode content={'one\ntwo\nthree'} />);
    expect(rowsOf(withoutFinalBreak.container)).toHaveLength(3);
    expect(withoutFinalBreak.container.textContent).toBe('one\ntwo\nthree');
  });

  it('shows an empty file as one empty row, like the editor does', () => {
    const { container } = render(<LineNumberedCode content="" />);
    expect(rowsOf(container)).toHaveLength(1);
    expect(container.textContent).toBe('');
  });

  it('leaves the numbers to CSS: nothing numeric is in the DOM, so they cannot be selected, copied or read aloud', () => {
    const { container } = render(<LineNumberedCode content={'a\nb\nc'} />);
    expect(container.querySelector('[aria-hidden="true"]')).toBeNull();
    expect(container.textContent).toBe('a\nb\nc');
  });

  it('tells the stylesheet how many digits the numbers have, so the text column stays aligned', () => {
    const digitsOf = (lineCount: number): string => {
      const { container, unmount } = render(<LineNumberedCode content={'x\n'.repeat(lineCount)} />);
      const value = container
        .querySelector<HTMLElement>('.numbered-code')
        ?.style.getPropertyValue('--numbered-code-digits');
      unmount();
      return value ?? '';
    };
    expect(digitsOf(1)).toBe('1');
    expect(digitsOf(9)).toBe('1');
    expect(digitsOf(10)).toBe('2');
    expect(digitsOf(1000)).toBe('4');
  });

  it('leaves font size and line height to the stylesheet: a text-size utility would override them and shift the rows off the numbers', () => {
    const { container } = render(<LineNumberedCode content="a" />);
    expect(container.querySelector('.numbered-code')?.className).not.toMatch(/\b(?:text-(?:xs|sm|base|lg)|leading-)/);
  });

  it('lets the browser skip off-screen rows only in long files, so a short file keeps an exact scrollbar', () => {
    const lazyOf = (lineCount: number): boolean => {
      const { container, unmount } = render(<LineNumberedCode content={'x\n'.repeat(lineCount)} />);
      const lazy = container.querySelector('.numbered-code')?.classList.contains('numbered-code-lazy') ?? false;
      unmount();
      return lazy;
    };
    expect(lazyOf(2000)).toBe(false);
    expect(lazyOf(2001)).toBe(true);
  });

  it('keeps showing a file with an extreme number of lines, as plain text without numbers', () => {
    const content = '\n'.repeat(100_001);
    const { container } = render(<LineNumberedCode content={content} />);
    expect(rowsOf(container)).toHaveLength(0);
    expect(container.querySelector('pre')?.textContent).toBe(content);
  });
});

describe('LineNumberedCode syntax highlighting', () => {
  const colouredSpans = (scope: ParentNode): HTMLElement[] =>
    Array.from(scope.querySelectorAll<HTMLElement>('span')).filter((span) => span.style.color !== '');

  const FIXTURES: Record<string, { language: string; content: string }> = {
    'a block comment and a template literal over several lines': {
      language: 'typescript',
      content: 'const a = `x\n${1}\ny`;\n/* one\n   two */\nfunction f() {}\n',
    },
    json: { language: 'json', content: '{\n  "a": [1, 2],\n  "b": null\n}\n' },
    'a python docstring': { language: 'python', content: 'def f():\n    """doc\n    string"""\n    return 1\n' },
    'markdown with a fence': { language: 'markdown', content: '# Title\n\n```ts\nconst a = 1;\n```\n' },
    'blank lines, tabs and trailing spaces': { language: 'tsx', content: 'a\n\n\tb \t\n  \nc' },
    'no final line break': { language: 'typescript', content: 'const a = 1;' },
    'CRLF line breaks': { language: 'typescript', content: 'const a = 1;\r\nconst b = 2;\r\n' },
    'a lone carriage return inside a line': { language: 'typescript', content: 'a\rb\nconst x = 1;\n' },
    'a lone carriage return that shifts later lines onto lines of the same length': {
      language: 'typescript',
      content: 'aaa\rbbb\nccc\n',
    },
    'non-ASCII text': { language: 'typescript', content: 'const s = "héllo 你好 🙂";\n' },
    'an empty file': { language: 'typescript', content: '' },
    'nothing but line breaks': { language: 'typescript', content: '\n\n\n' },
  };

  it.each(Object.entries(FIXTURES))('shows %s exactly as plain text does: same text, same rows', (_name, fixture) => {
    const plain = render(<LineNumberedCode content={fixture.content} />);
    const plainRows = rowsOf(plain.container).length;
    plain.unmount();

    const { container } = render(<LineNumberedCode content={fixture.content} language={fixture.language} />);

    expect(container.textContent).toBe(fixture.content);
    expect(rowsOf(container)).toHaveLength(plainRows);
  });

  it('colours the tokens of a known language', () => {
    const { container } = render(<LineNumberedCode content={'const answer = 42;\n'} language="typescript" />);

    expect(colouredSpans(container).find((span) => span.textContent === 'const')).toBeTruthy();
  });

  it('reads the file as one source: a block comment keeps its colour on every row it covers', () => {
    const { container } = render(
      <LineNumberedCode content={'/* first\nconst inside = 1;\n*/\nconst outside = 2;\n'} language="typescript" />,
    );
    const [first, inside, closing, outside] = rowsOf(container);

    const commentColour = colouredSpans(first)[0]?.style.color;
    expect(commentColour).toBeTruthy();
    expect(colouredSpans(inside).map((span) => span.style.color)).toEqual([commentColour]);
    expect(colouredSpans(closing).map((span) => span.style.color)).toEqual([commentColour]);
    expect(colouredSpans(outside).find((span) => span.textContent === 'const')?.style.color).not.toBe(commentColour);
  });

  it('keeps every row with its own tokens when the line breaks are CRLF', () => {
    const { container } = render(
      <LineNumberedCode content={'const a = 1;\r\nconst b = 2;\r\n'} language="typescript" />,
    );

    for (const row of rowsOf(container)) {
      expect(colouredSpans(row).find((span) => span.textContent === 'const')).toBeTruthy();
    }
  });

  it('shows a row plain when the highlighter split the file differently than the rows: a lone carriage return', () => {
    const { container } = render(<LineNumberedCode content={'const\rconst x\nconst x = 1;\n'} language="typescript" />);

    for (const row of rowsOf(container)) {
      expect(colouredSpans(row)).toHaveLength(0);
    }
  });

  it('highlights up to the lazy-rendering threshold and stays plain beyond it', () => {
    const line = 'const a = 1;\n';
    const atThreshold = render(<LineNumberedCode content={line.repeat(2000)} language="typescript" />);
    expect(colouredSpans(atThreshold.container).length).toBeGreaterThan(0);
    atThreshold.unmount();

    const content = line.repeat(2001);
    const beyond = render(<LineNumberedCode content={content} language="typescript" />);
    expect(colouredSpans(beyond.container)).toHaveLength(0);
    expect(beyond.container.textContent).toBe(content);
  });

  it('highlights up to 100,000 characters and stays plain beyond them', () => {
    const hundredCharComments = `//${'x'.repeat(97)}\n`.repeat(1_000);

    const atLimit = render(<LineNumberedCode content={hundredCharComments} language="typescript" />);
    expect(colouredSpans(atLimit.container)).toHaveLength(1_000);
    atLimit.unmount();

    const beyond = render(<LineNumberedCode content={`${hundredCharComments}y`} language="typescript" />);
    expect(colouredSpans(beyond.container)).toHaveLength(0);
    expect(beyond.container.textContent).toBe(`${hundredCharComments}y`);
  });

  it('stays plain when the file has more tokens than the page takes cheaply, however few its rows and characters', () => {
    const dense = `${'1,'.repeat(1_000)}\n`.repeat(15);
    const { container } = render(<LineNumberedCode content={dense} language="javascript" />);

    expect(colouredSpans(container)).toHaveLength(0);
    expect(container.textContent).toBe(dense);
  });

  it('stays plain when a line is past the length Prism handles in bounded time, whatever the rest of the file is', () => {
    const content = `const a = 1;\n// ${'x'.repeat(MAX_HIGHLIGHT_LINE_CHARS)}\n`;
    const { container } = render(<LineNumberedCode content={content} language="typescript" />);

    expect(colouredSpans(container)).toHaveLength(0);
    expect(container.textContent).toBe(content);
  });

  it('still colours a short line made of many tokens', () => {
    const { container } = render(<LineNumberedCode content={'1,'.repeat(1_000)} language="javascript" />);

    expect(colouredSpans(container).length).toBeGreaterThan(1_000);
  });

  it.each([undefined, 'text', 'no-such-language'])('stays plain without a grammar for it (%s)', (language) => {
    const { container } = render(<LineNumberedCode content={'const a = 1;\n'} language={language} />);

    expect(colouredSpans(container)).toHaveLength(0);
    expect(container.textContent).toBe('const a = 1;\n');
  });

  it('keeps showing a file with an extreme number of lines as plain text, whatever its language', () => {
    const content = '\n'.repeat(100_001);
    const { container } = render(<LineNumberedCode content={content} language="typescript" />);

    expect(rowsOf(container)).toHaveLength(0);
    expect(container.querySelector('pre')?.textContent).toBe(content);
  });

  it('follows the app theme', () => {
    const keywordColour = (): string | undefined => {
      const { container, unmount } = render(<LineNumberedCode content={'const a = 1;\n'} language="typescript" />);
      const colour = colouredSpans(container).find((span) => span.textContent === 'const')?.style.color;
      unmount();
      return colour;
    };

    appTheme.resolved = 'light';
    const light = keywordColour();
    appTheme.resolved = 'dark';
    const dark = keywordColour();
    appTheme.resolved = 'light';

    expect(light).toBeTruthy();
    expect(dark).toBeTruthy();
    expect(light).not.toBe(dark);
  });
});
