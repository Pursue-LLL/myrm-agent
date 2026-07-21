import { describe, expect, it } from 'vitest';

import { generateStreamRequestMessageId } from '../streamRequestMessageId';

describe('generateStreamRequestMessageId', () => {
  it('returns unique r- prefixed ids', () => {
    const first = generateStreamRequestMessageId();
    const second = generateStreamRequestMessageId();
    expect(first).toMatch(/^r-/);
    expect(second).toMatch(/^r-/);
    expect(first).not.toBe(second);
  });
});
