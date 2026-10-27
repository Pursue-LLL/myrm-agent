import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { PastedTextCard } from '../PastedTextCard';

// The global next-intl stub renders every translation key as itself.
const FULL_TEXT = 'line one\nline two';

describe('PastedTextCard', () => {
  it('shows the opening lines and offers to open the stored full text', () => {
    const onOpen = vi.fn();
    render(<PastedTextCard chars={48_000} preview="Q3 review" onOpen={onOpen} />);

    expect(screen.getByText('Q3 review')).not.toBeNull();
    fireEvent.click(screen.getByRole('button', { name: 'pastedText.viewFull' }));

    expect(onOpen).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole('button', { name: 'pastedText.expand' })).toBeNull();
  });

  it('unfolds a text still in memory in place, and folds it again', () => {
    render(<PastedTextCard chars={17_000} preview="line one" fullText={FULL_TEXT} />);
    const toggle = screen.getByRole('button', { name: 'pastedText.expand' });

    expect(toggle.getAttribute('aria-expanded')).toBe('false');
    fireEvent.click(toggle);

    expect(screen.getByText((_, node) => node?.textContent === FULL_TEXT && node.tagName === 'DIV')).not.toBeNull();
    expect(screen.getByRole('button', { name: 'pastedText.collapse' }).getAttribute('aria-expanded')).toBe('true');

    fireEvent.click(screen.getByRole('button', { name: 'pastedText.collapse' }));

    expect(screen.queryByText((_, node) => node?.textContent === FULL_TEXT && node.tagName === 'DIV')).toBeNull();
  });

  it('shows no preview line for a paste stored before previews were kept', () => {
    const { container } = render(<PastedTextCard chars={9} preview="" onOpen={vi.fn()} />);

    expect(container.querySelector('p.line-clamp-3')).toBeNull();
  });
});
