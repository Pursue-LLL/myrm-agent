import { act, render } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { TooltipProvider } from '@/components/primitives/tooltip';
import CodeBlock from '../CodeBlock';

vi.mock('next-themes', () => ({
  useTheme: () => ({ theme: 'light', resolvedTheme: 'light' }),
}));

const stableT = (key: string) => key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
  useLocale: () => 'en',
}));

const FIRST = 'const first = 1;';
const SECOND = 'const second = 2;';
const THIRD = 'const third = 3;';

function block(value: string, isStreaming: boolean) {
  return (
    <TooltipProvider>
      <CodeBlock language="typescript" value={value} isStreaming={isStreaming} />
    </TooltipProvider>
  );
}

function advance(ms: number) {
  act(() => {
    vi.advanceTimersByTime(ms);
  });
}

describe('CodeBlock streaming debounce', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('shows a streamed update only after the 100ms debounce window', () => {
    const { container, rerender } = render(block(FIRST, true));

    rerender(block(SECOND, true));
    expect(container.textContent).toContain('first');
    expect(container.textContent).not.toContain('second');

    advance(99);
    expect(container.textContent).not.toContain('second');

    advance(1);
    expect(container.textContent).toContain('second');
    expect(container.textContent).not.toContain('first');
  });

  it('restarts the window on every update and never renders the superseded value', () => {
    const { container, rerender } = render(block(FIRST, true));

    rerender(block(SECOND, true));
    advance(60);
    rerender(block(THIRD, true));
    advance(60);
    expect(container.textContent).toContain('first');

    advance(40);
    expect(container.textContent).toContain('third');
    expect(container.textContent).not.toContain('second');
  });

  it('shows the final value at once when streaming ends', () => {
    const { container, rerender } = render(block(FIRST, true));

    rerender(block(SECOND, true));
    rerender(block(THIRD, false));

    expect(container.textContent).toContain('third');
    expect(container.textContent).not.toContain('first');
  });

  it('resumes streaming from the latest content and ignores the timer cancelled when streaming ended', () => {
    const { container, rerender } = render(block(FIRST, true));

    rerender(block(SECOND, true));
    rerender(block(THIRD, false));
    rerender(block(THIRD, true));

    expect(container.textContent).toContain('third');
    expect(container.textContent).not.toContain('first');

    advance(200);
    expect(container.textContent).toContain('third');
    expect(container.textContent).not.toContain('second');
  });
});
