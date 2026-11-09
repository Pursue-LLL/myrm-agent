import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import type { CompletionStatus } from '@/store/chat/types';
import { CompletionStatusNotice } from '../CompletionStatusNotice';

const stableT = (key: string) => key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

describe('CompletionStatusNotice', () => {
  it.each([
    ['truncated', 'message.truncated', 'bg-amber-50'],
    ['cancelled', 'message.cancelled', 'bg-muted/40'],
    ['filtered', 'message.contentFiltered', 'bg-red-50'],
    ['budget_blocked', 'message.budgetBlocked', 'bg-orange-50'],
  ] as const)('explains a reply that ended as %s', (status, label, tone) => {
    const { container } = render(<CompletionStatusNotice status={status} streaming={false} />);

    expect(screen.getByText(label)).toBeTruthy();
    expect(container.firstElementChild?.className).toContain(tone);
    expect(container.querySelector('svg')).not.toBeNull();
  });

  it('keeps the neutral banner free of a tone of its own on the text', () => {
    render(<CompletionStatusNotice status="cancelled" streaming={false} />);

    expect(screen.getByText('message.cancelled').hasAttribute('class')).toBe(false);
  });

  it.each(['truncated', 'cancelled', 'filtered', 'budget_blocked'] as const)(
    'shows nothing for %s while the answer is still streaming',
    (status) => {
      const { container } = render(<CompletionStatusNotice status={status} streaming />);

      expect(container.innerHTML).toBe('');
    },
  );

  it.each<CompletionStatus | undefined>(['complete', 'success', 'error', undefined])(
    'shows nothing for a reply that ended as %s',
    (status) => {
      const { container } = render(<CompletionStatusNotice status={status} streaming={false} />);

      expect(container.innerHTML).toBe('');
    },
  );

  it('shows nothing for a status it does not know, even one named like an object property', () => {
    const { container } = render(
      <CompletionStatusNotice status={'constructor' as unknown as CompletionStatus} streaming={false} />,
    );

    expect(container.innerHTML).toBe('');
  });
});
