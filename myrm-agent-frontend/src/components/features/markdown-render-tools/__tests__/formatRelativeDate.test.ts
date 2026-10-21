import { describe, it, expect, vi } from 'vitest';
import { formatRelativeDate } from '../LinkPopover';

const mockT = vi.fn((key: string, values?: Record<string, number>) => {
  const templates: Record<string, string> = {
    'relativeDate.today': 'Today',
    'relativeDate.yesterday': 'Yesterday',
    'relativeDate.daysAgo': `${values?.count}d ago`,
    'relativeDate.weeksAgo': `${values?.count}w ago`,
    'relativeDate.monthsAgo': `${values?.count}mo ago`,
  };
  return templates[key] ?? key;
});

function daysAgo(n: number): string {
  const d = new Date();
  d.setDate(d.getDate() - n);
  return d.toISOString();
}

describe('formatRelativeDate', () => {
  it('returns translated "today" for same-day dates', () => {
    expect(formatRelativeDate(new Date().toISOString(), mockT)).toBe('Today');
    expect(mockT).toHaveBeenCalledWith('relativeDate.today');
  });

  it('returns translated "yesterday" for 1-day-old dates', () => {
    expect(formatRelativeDate(daysAgo(1), mockT)).toBe('Yesterday');
    expect(mockT).toHaveBeenCalledWith('relativeDate.yesterday');
  });

  it('returns "{count}d ago" for 2-6 day range', () => {
    expect(formatRelativeDate(daysAgo(3), mockT)).toBe('3d ago');
    expect(mockT).toHaveBeenCalledWith('relativeDate.daysAgo', { count: 3 });

    expect(formatRelativeDate(daysAgo(6), mockT)).toBe('6d ago');
    expect(mockT).toHaveBeenCalledWith('relativeDate.daysAgo', { count: 6 });
  });

  it('returns "{count}w ago" for 7-29 day range', () => {
    expect(formatRelativeDate(daysAgo(7), mockT)).toBe('1w ago');
    expect(formatRelativeDate(daysAgo(14), mockT)).toBe('2w ago');
    expect(formatRelativeDate(daysAgo(20), mockT)).toBe('2w ago');
  });

  it('returns "{count}mo ago" for 30-364 day range', () => {
    expect(formatRelativeDate(daysAgo(30), mockT)).toBe('1mo ago');
    expect(formatRelativeDate(daysAgo(60), mockT)).toBe('2mo ago');
    expect(formatRelativeDate(daysAgo(364), mockT)).toBe('12mo ago');
  });

  it('returns ISO date for dates >= 365 days old', () => {
    const old = new Date('2020-03-15T00:00:00Z');
    expect(formatRelativeDate(old.toISOString(), mockT)).toBe('2020-03-15');
  });

  it('returns raw string for invalid date input', () => {
    expect(formatRelativeDate('not-a-date', mockT)).toBe('not-a-date');
    expect(formatRelativeDate('', mockT)).toBe('');
  });

  it('returns raw string for future dates', () => {
    const future = new Date();
    future.setDate(future.getDate() + 5);
    expect(formatRelativeDate(future.toISOString(), mockT)).toBe(future.toISOString());
  });
});
