import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { WakeupNoticeRow } from '../WakeupNoticeRow';

// The global next-intl stub renders every translation key as itself.
describe('WakeupNoticeRow', () => {
  it('tells the user the paused follow-ups wait for a message', () => {
    render(<WakeupNoticeRow kind="degraded" />);

    expect(screen.getByRole('status').getAttribute('data-kind')).toBe('degraded');
    expect(screen.getByText('wakeupNotice.degraded')).toBeDefined();
  });

  it('tells the user a task finished while the chat was stopped', () => {
    render(<WakeupNoticeRow kind="suppressed" />);

    expect(screen.getByText('wakeupNotice.suppressed')).toBeDefined();
  });

  it('keeps the decorative rules out of the accessibility tree', () => {
    const { container } = render(<WakeupNoticeRow kind="degraded" />);

    const rules = container.querySelectorAll('span[aria-hidden="true"]');
    expect(rules).toHaveLength(2);
  });
});
