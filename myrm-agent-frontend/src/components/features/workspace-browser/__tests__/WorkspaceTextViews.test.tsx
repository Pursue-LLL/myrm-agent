/** @vitest-environment jsdom */
import { fireEvent, render, screen } from '@testing-library/react';
import { useState } from 'react';
import { describe, expect, it } from 'vitest';
import { LineNumberedCode, LineNumberedEditor } from '../WorkspaceTextViews';

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

describe('LineNumberedCode', () => {
  const rowsOf = (container: HTMLElement): HTMLElement[] =>
    Array.from(container.querySelectorAll<HTMLElement>('.numbered-code-line'));

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
