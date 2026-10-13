import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import UserMessage from '../UserMessage';

const quote = vi.hoisted(() => ({ selection: { state: null, dismiss: () => undefined } }));

vi.mock('../QuoteToolbar', () => ({
  QuoteToolbar: () => null,
  useQuoteSelection: () => quote.selection,
}));
vi.mock('../SkillActivationChips', () => ({ SkillActivationChips: () => null }));
vi.mock('../../chat-window/ForkButton', () => ({ ForkButton: () => null }));
vi.mock('../../chat-window/RewindButton', () => ({ RewindButton: () => null }));
vi.mock('../../message-input-actions/ImageLightbox', () => ({ ImageLightbox: () => null }));

// The global next-intl stub renders every translation key as itself.
const RETRY = 'retry';
const bubble = { content: 'hello there', messageId: 'u-1', isFirst: false };

describe('UserMessage failed send', () => {
  it('offers a retry under a bubble whose send failed', () => {
    const onRetry = vi.fn();
    render(<UserMessage {...bubble} sendFailed onRetry={onRetry} />);

    fireEvent.click(screen.getByRole('button', { name: RETRY }));

    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it('offers no retry under a delivered bubble', () => {
    render(<UserMessage {...bubble} onRetry={vi.fn()} />);

    expect(screen.queryByRole('button', { name: RETRY })).toBeNull();
  });

  it('offers no retry while the bubble is being edited', () => {
    render(<UserMessage {...bubble} sendFailed isEditing onRetry={vi.fn()} />);

    expect(screen.queryByRole('button', { name: RETRY })).toBeNull();
  });
});

describe('UserMessage @links', () => {
  it('opens a bare domain over https in a new tab that cannot reach back to the page', () => {
    render(<UserMessage {...bubble} content="see @example.com/docs now" />);

    const link = screen.getByRole('link', { name: '@example.com/docs' });

    expect(link.getAttribute('href')).toBe('https://example.com/docs');
    expect(link.getAttribute('target')).toBe('_blank');
    expect(link.getAttribute('rel')).toBe('noopener noreferrer');
  });

  it('keeps the address of an @link that already carries a scheme', () => {
    render(<UserMessage {...bubble} content="open @http://localhost:3000/x" />);

    expect(screen.getByRole('link', { name: '@http://localhost:3000/x' }).getAttribute('href')).toBe(
      'http://localhost:3000/x',
    );
  });
});
