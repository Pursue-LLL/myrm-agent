import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { SendFailedNotice } from '../SendFailedNotice';

// The global next-intl stub renders every translation key as itself.
const HINT = 'messageFailed.networkError';
const RETRY = 'retry';

describe('SendFailedNotice', () => {
  it('offers a retry action next to the connection hint', () => {
    const onRetry = vi.fn();
    render(<SendFailedNotice onRetry={onRetry} />);

    expect(screen.getByText(HINT)).toBeDefined();
    fireEvent.click(screen.getByRole('button', { name: RETRY }));

    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  // jsdom computes no layout, so the layout contract is pinned through its two causes. Measured in a browser on a
  // 343px column: when the hint fills the line, a button that may shrink gets its label broken apart (one character
  // per line in Chinese, Japanese and Korean, one word per line in German).
  it('lets the line wrap so a long hint takes rows of its own', () => {
    render(<SendFailedNotice onRetry={vi.fn()} />);

    expect(screen.getByText(HINT).parentElement?.classList.contains('flex-wrap')).toBe(true);
  });

  it('keeps the retry button at its natural size', () => {
    render(<SendFailedNotice onRetry={vi.fn()} />);

    const button = screen.getByRole('button', { name: RETRY });
    expect(button.classList.contains('shrink-0')).toBe(true);
    expect(button.classList.contains('whitespace-nowrap')).toBe(true);
  });
});
