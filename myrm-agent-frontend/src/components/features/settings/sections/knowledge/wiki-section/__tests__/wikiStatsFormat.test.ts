import { describe, expect, it } from 'vitest';
import { formatCognitiveUpdatedAt, maintainSkippedBadgeLabel } from '../wikiStatsFormat';

// Midday UTC lands on the 15th in every real time zone give or take a day, so the pattern allows 14 to 16.
const INSTANT = '2026-01-15T12:00:00Z';

describe('formatCognitiveUpdatedAt', () => {
  it.each([null, undefined, ''])('shows nothing when the time is %j', (missing) => {
    expect(formatCognitiveUpdatedAt(missing, 'en')).toBe('');
  });

  it('hands an unreadable value back untouched instead of printing "Invalid Date"', () => {
    expect(formatCognitiveUpdatedAt('last tuesday', 'en')).toBe('last tuesday');
  });

  it('writes the date and the time of day in the language of the interface', () => {
    expect(formatCognitiveUpdatedAt(INSTANT, 'en')).toMatch(/^Jan 1[456], 2026, \d{1,2}:\d{2}\s[AP]M$/);
    expect(formatCognitiveUpdatedAt(INSTANT, 'ja')).toMatch(/^2026\/01\/1[456] \d{2}:\d{2}$/);
    expect(formatCognitiveUpdatedAt(INSTANT, 'de')).toMatch(/^1[456]\.01\.2026, \d{2}:\d{2}$/);
  });
});

describe('maintainSkippedBadgeLabel', () => {
  const translate = (key: string) => `t:${key}`;

  it('says the maintenance waited for a compile when that was the reason', () => {
    expect(maintainSkippedBadgeLabel('compile_in_progress', translate)).toBe('t:stats.lastMaintainSkippedCompile');
  });

  it.each(['ai_unavailable', '', 'anything else'])('uses the generic skipped label for %j', (reason) => {
    expect(maintainSkippedBadgeLabel(reason, translate)).toBe('t:stats.lastMaintainSkipped');
  });
});
