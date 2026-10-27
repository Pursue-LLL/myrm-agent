import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { SPILLOVER_MIN_CHARS } from '@/lib/utils/spillover';

import { ContextSpilloverBadge } from '../ContextSpilloverBadge';

describe('ContextSpilloverBadge', () => {
  it('stays hidden for a text the chat can carry as is', () => {
    render(<ContextSpilloverBadge charCount={SPILLOVER_MIN_CHARS} />);

    expect(screen.queryByTestId('context-spillover-badge')).toBeNull();
  });

  it('tells the person a longer text is kept with the chat', () => {
    render(<ContextSpilloverBadge charCount={SPILLOVER_MIN_CHARS + 1} />);

    expect(screen.getByTestId('context-spillover-badge').textContent).toBe('spillover.notice');
  });
});
