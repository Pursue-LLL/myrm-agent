import { describe, expect, it } from 'vitest';

import { formatRelativeTime } from '../relativeTime';

describe('formatRelativeTime', () => {
  it('formats a valid ISO timestamp as a localized relative time', () => {
    expect(formatRelativeTime(new Date().toISOString(), 'en')).not.toBe('');
    expect(formatRelativeTime(new Date().toISOString(), 'zh')).not.toBe('');
  });

  it('returns an empty string for an invalid timestamp', () => {
    expect(formatRelativeTime('not-a-date', 'en')).toBe('');
    expect(formatRelativeTime('', 'en')).toBe('');
  });

  it('buckets diffs into second/minute/hour/day phrasing', () => {
    const now = Date.now();
    expect(formatRelativeTime(new Date(now - 30_000).toISOString(), 'en')).toMatch(/second|minut/i);
    expect(formatRelativeTime(new Date(now - 90_000).toISOString(), 'en')).toMatch(/minut/i);
    expect(formatRelativeTime(new Date(now - 2 * 3600_000).toISOString(), 'en')).toMatch(/hour/i);
    expect(formatRelativeTime(new Date(now - 2 * 86400_000).toISOString(), 'en')).toMatch(/day/i);
  });
});
