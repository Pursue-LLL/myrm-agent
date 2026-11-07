import { afterEach, describe, expect, it, vi } from 'vitest';

import { handleLinkClick } from '../utils';

afterEach(() => {
  vi.restoreAllMocks();
});

describe('handleLinkClick', () => {
  it('opens a valid link in a new tab without an opener', () => {
    const open = vi.spyOn(window, 'open').mockReturnValue(null);

    handleLinkClick('https://example.com/a', true);

    expect(open).toHaveBeenCalledExactlyOnceWith('https://example.com/a', '_blank', 'noopener,noreferrer');
  });

  it('adds https to a bare www. host', () => {
    const open = vi.spyOn(window, 'open').mockReturnValue(null);

    handleLinkClick('www.example.com/a', true);

    expect(open).toHaveBeenCalledExactlyOnceWith('https://www.example.com/a', '_blank', 'noopener,noreferrer');
  });

  it('opens nothing for a link its caller found invalid', () => {
    const open = vi.spyOn(window, 'open').mockReturnValue(null);

    handleLinkClick('https://example.com/a', false);

    expect(open).not.toHaveBeenCalled();
  });
});
