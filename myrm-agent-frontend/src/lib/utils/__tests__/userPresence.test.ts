/** @vitest-environment jsdom */

import { afterEach, describe, expect, it, vi } from 'vitest';

import { isUserPresent } from '../userPresence';

describe('isUserPresent', () => {
  afterEach(() => {
    vi.restoreAllMocks();
    Object.defineProperty(document, 'hidden', { configurable: true, value: false });
  });

  it.each([
    [false, true, true],
    [true, true, false],
    [false, false, false],
    [true, false, false],
  ])('hidden=%s focused=%s -> %s', (hidden, focused, expected) => {
    Object.defineProperty(document, 'hidden', { configurable: true, value: hidden });
    vi.spyOn(document, 'hasFocus').mockReturnValue(focused);

    expect(isUserPresent()).toBe(expected);
  });
});
