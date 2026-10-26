/** @vitest-environment jsdom */
import { fireEvent, render, screen } from '@testing-library/react';
import { useState } from 'react';
import { describe, expect, it } from 'vitest';
import { LineNumberedCode, LineNumberedEditor } from '../WorkspaceTextViews';

function Editor({ initial }: { initial: string }) {
  const [content, setContent] = useState(initial);
  return <LineNumberedEditor content={content} onChange={setContent} />;
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

  it('scrolls the numbers together with the text', () => {
    const { container } = render(<Editor initial={'a\nb\nc'} />);
    const textbox = screen.getByRole('textbox');

    textbox.scrollTop = 120;
    fireEvent.scroll(textbox);

    expect(gutterOf(container).scrollTop).toBe(120);
  });
});

describe('LineNumberedCode', () => {
  it('numbers the lines of the read-only view and shows the text as it is', () => {
    const { container } = render(<LineNumberedCode content={'one\ntwo\nthree'} language="plaintext" />);
    expect(gutterOf(container).textContent).toBe('1\n2\n3');
    expect(container.querySelector('code')?.textContent).toBe('one\ntwo\nthree');
    expect(container.querySelector('code')?.getAttribute('data-language')).toBe('plaintext');
  });
});
