import { act, fireEvent, render, screen } from '@testing-library/react';
import type { FormEvent, ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import useQuoteStore from '@/store/useQuoteStore';

import { QuoteCard } from '../QuoteCard';

vi.mock('next-intl', async () => (await import('@/test-utils/realIntl')).createRealIntlMock(() => 'en'));
vi.mock('framer-motion', () => ({
  motion: {
    div: ({ children, className }: { children: ReactNode; className?: string }) => (
      <div className={className}>{children}</div>
    ),
  },
  AnimatePresence: ({ children }: { children: ReactNode }) => <>{children}</>,
}));

const quote = (text: string) =>
  act(() => useQuoteStore.getState().setQuote({ sourceMessageId: 'm-1', quotedText: text }));

beforeEach(() => {
  useQuoteStore.setState({ quote: null });
});

describe('QuoteCard', () => {
  it('shows nothing while there is no quote', () => {
    const { container } = render(<QuoteCard />);

    expect(container).toBeEmptyDOMElement();
  });

  it('shows the quoted text as soon as there is a quote', () => {
    render(<QuoteCard />);

    quote('what the assistant said');

    expect(screen.getByText('what the assistant said')).toBeInTheDocument();
  });

  it('keeps a text of exactly 120 characters whole and cuts a longer one with an ellipsis', () => {
    render(<QuoteCard />);
    const whole = 'a'.repeat(120);

    quote(whole);
    expect(screen.getByText(whole)).toBeInTheDocument();

    quote(`${whole}b`);
    expect(screen.getByText(`${whole}…`)).toBeInTheDocument();
    expect(screen.queryByText(`${whole}b`)).toBeNull();
  });

  it('is dropped by a button that says what it does, and the quote is gone from the store', () => {
    render(<QuoteCard />);
    quote('to be removed');

    fireEvent.click(screen.getByRole('button', { name: 'Remove quote' }));

    expect(useQuoteStore.getState().quote).toBeNull();
    expect(screen.queryByText('to be removed')).toBeNull();
  });

  it('is a plain button, so removing the quote never submits a surrounding form', () => {
    const onSubmit = vi.fn((event: FormEvent) => event.preventDefault());
    render(
      <form onSubmit={onSubmit}>
        <QuoteCard />
      </form>,
    );
    quote('inside a form');

    fireEvent.click(screen.getByRole('button', { name: 'Remove quote' }));

    expect(onSubmit).not.toHaveBeenCalled();
    expect(useQuoteStore.getState().quote).toBeNull();
  });
});
