import { describe, expect, it } from 'vitest';
import { formatDuration } from '../timeUtils';

describe('formatDuration', () => {
  it('formats seconds only', () => {
    const start = '2026-08-12T00:00:00.000Z';
    expect(formatDuration(start, '2026-08-12T00:00:42.000Z')).toBe('42s');
  });

  it('formats minutes with seconds', () => {
    const start = '2026-08-12T00:00:00.000Z';
    expect(formatDuration(start, '2026-08-12T00:08:30.000Z')).toBe('8m 30s');
  });

  it('formats whole minutes', () => {
    const start = '2026-08-12T00:00:00.000Z';
    expect(formatDuration(start, '2026-08-12T00:10:00.000Z')).toBe('10m');
  });

  it('formats hours with minutes', () => {
    const start = '2026-08-12T00:00:00.000Z';
    expect(formatDuration(start, '2026-08-12T01:05:00.000Z')).toBe('1h 5m');
  });

  it('formats whole hours', () => {
    const start = '2026-08-12T00:00:00.000Z';
    expect(formatDuration(start, '2026-08-12T01:00:00.000Z')).toBe('1h');
  });

  it('returns placeholder when a timestamp is missing', () => {
    expect(formatDuration(null, '2026-08-12T00:00:42.000Z')).toBe('—');
    expect(formatDuration('2026-08-12T00:00:00.000Z', null)).toBe('—');
    expect(formatDuration(undefined, undefined)).toBe('—');
  });

  it('returns placeholder when timestamps are invalid', () => {
    expect(formatDuration('not-a-date', '2026-08-12T00:00:42.000Z')).toBe('—');
  });

  it('returns placeholder when end precedes start', () => {
    const start = '2026-08-12T00:00:42.000Z';
    const end = '2026-08-12T00:00:00.000Z';
    expect(formatDuration(start, end)).toBe('—');
  });

  it('formats zero seconds', () => {
    const start = '2026-08-12T00:00:00.000Z';
    expect(formatDuration(start, start)).toBe('0s');
  });
});
