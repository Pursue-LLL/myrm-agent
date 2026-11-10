import { render } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { ScrollArea } from '../scroll-area';

describe('ScrollArea', () => {
  // Layout is not computed in jsdom; the browser behaviour (a root capped only by max-height scrolls instead of
  // clipping) was measured separately, so this guards the class that provides it.
  it('lets the viewport repeat the root max-height so a capped root scrolls', () => {
    const { container } = render(
      <ScrollArea className="max-h-32">
        <p>content</p>
      </ScrollArea>,
    );

    const viewport = container.querySelector('[data-radix-scroll-area-viewport]');
    expect(viewport).toHaveClass('max-h-[inherit]');
  });
});
