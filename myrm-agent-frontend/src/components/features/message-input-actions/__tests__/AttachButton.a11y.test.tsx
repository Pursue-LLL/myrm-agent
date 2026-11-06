/** @vitest-environment jsdom */
import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { TooltipProvider } from '@/components/primitives/tooltip';

import AttachButton from '../AttachButton';

describe('AttachButton', () => {
  it('is announced by name instead of as an anonymous button', () => {
    render(
      <TooltipProvider>
        <AttachButton files={[]} setFiles={vi.fn()} />
      </TooltipProvider>,
    );

    expect(screen.getByRole('button', { name: 'attach' })).toBeTruthy();
  });
});
