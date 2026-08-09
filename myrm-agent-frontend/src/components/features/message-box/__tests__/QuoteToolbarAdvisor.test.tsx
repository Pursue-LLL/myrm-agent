'use client';

import { render, screen, fireEvent } from '@testing-library/react';
import { describe, expect, it, vi, beforeEach } from 'vitest';

const stableT = (key: string) => key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

vi.mock('@/store/useChatStore', () => ({
  __esModule: true,
  default: (selector: (s: { loading: boolean }) => unknown) =>
    selector({ loading: true }),
}));

vi.mock('@/store/useQuoteStore', () => ({
  __esModule: true,
  default: { getState: () => ({ setQuote: vi.fn() }) },
}));

vi.mock('@/lib/utils/clipboardUtils', () => ({
  writeToClipboard: vi.fn(),
}));

vi.mock('framer-motion', () => ({
  motion: {
    div: ({ children, ...props }: React.PropsWithChildren<Record<string, unknown>>) => (
      <div {...props}>{children}</div>
    ),
  },
  AnimatePresence: ({ children }: React.PropsWithChildren) => <>{children}</>,
}));

import { QuoteToolbar } from '../QuoteToolbar';

describe('QuoteToolbar advisor dispatch', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('dispatches copilot-open-advisor with selection while loading', () => {
    const handler = vi.fn();
    window.addEventListener('copilot-open-advisor', handler);

    render(
      <QuoteToolbar
        state={{
          visible: true,
          text: 'stderr: connection refused',
          isCode: false,
          rect: { x: 0, y: 0 },
          flipDown: false,
          sourceMessageId: 'msg-1',
        }}
        onDismiss={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByTitle('advisorSelectionAsk'));

    expect(handler).toHaveBeenCalledTimes(1);
    const event = handler.mock.calls[0][0] as CustomEvent<{
      question?: string;
      selection?: string;
    }>;
    expect(event.detail.selection).toBe('stderr: connection refused');

    window.removeEventListener('copilot-open-advisor', handler);
  });
});
