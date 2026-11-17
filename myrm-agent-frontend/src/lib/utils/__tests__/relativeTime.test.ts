import { describe, expect, it } from 'vitest';

import { formatRelativeTime } from '../relativeTime';

// What the formatter itself says for "no gap": the wording a clamped timestamp must share.
function noGapPhrase(locale: string): string {
  return new Intl.RelativeTimeFormat(locale, { numeric: 'auto' }).format(0, 'second');
}

describe('formatRelativeTime', () => {
  it('formats a valid ISO timestamp as a localized relative time', () => {
    expect(formatRelativeTime(new Date().toISOString(), 'en')).not.toBe('');
    expect(formatRelativeTime(new Date().toISOString(), 'zh')).not.toBe('');
  });

  it('reads an offset-less server timestamp as UTC, not local time', () => {
    const naiveUtcThirtySecondsAgo = new Date(Date.now() - 30_000).toISOString().replace('Z', '');
    expect(formatRelativeTime(naiveUtcThirtySecondsAgo, 'en')).toMatch(/second|minut/i);
    expect(formatRelativeTime(naiveUtcThirtySecondsAgo, 'en')).not.toMatch(/hour/i);
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

  it('reads a timestamp ahead of this device clock as now, never as a future time', () => {
    const aheadBySeconds = new Date(Date.now() + 3_000).toISOString();

    expect(formatRelativeTime(aheadBySeconds, 'en')).toBe(noGapPhrase('en'));
    expect(formatRelativeTime(aheadBySeconds, 'zh')).toBe(noGapPhrase('zh'));
  });

  it('clamps a large clock skew in every bucket, not only in seconds', () => {
    const aheadByHours = new Date(Date.now() + 2 * 3600_000).toISOString();

    expect(formatRelativeTime(aheadByHours, 'en')).toBe(noGapPhrase('en'));
  });

  it('keeps a past timestamp as a past phrase', () => {
    expect(formatRelativeTime(new Date(Date.now() - 5 * 60_000).toISOString(), 'en')).toBe('5 minutes ago');
  });

  it('buckets long-lived diffs into month/year phrasing', () => {
    const now = Date.now();
    expect(formatRelativeTime(new Date(now - 45 * 86400_000).toISOString(), 'en')).toMatch(/month/i);
    expect(formatRelativeTime(new Date(now - 400 * 86400_000).toISOString(), 'en')).toMatch(/year/i);
    expect(formatRelativeTime(new Date(now - 45 * 86400_000).toISOString(), 'zh')).toMatch(/月/);
    expect(formatRelativeTime(new Date(now - 400 * 86400_000).toISOString(), 'zh')).toMatch(/年/);
  });
});
