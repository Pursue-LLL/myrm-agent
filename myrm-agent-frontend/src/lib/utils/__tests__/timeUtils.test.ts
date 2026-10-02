import { describe, it, expect } from 'vitest';
import { formatDuration, getCurrentTimestamp, formatMessageTimestamp } from '../timeUtils';

describe('timeUtils', () => {
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

  describe('getCurrentTimestamp', () => {
    it('should return current timestamp in seconds', () => {
      const before = Date.now() / 1000;
      const result = getCurrentTimestamp();
      const after = Date.now() / 1000;

      expect(result).toBeGreaterThanOrEqual(before);
      expect(result).toBeLessThanOrEqual(after);
    });

    it('should return a number', () => {
      expect(typeof getCurrentTimestamp()).toBe('number');
    });
  });

  describe('formatMessageTimestamp', () => {
    it('should show HH:mm for today', () => {
      const now = new Date();
      now.setHours(14, 30, 0, 0);
      const result = formatMessageTimestamp(now, 'en', 'Yesterday');
      expect(result.label).toBe('14:30');
      expect(result.title).toBeTruthy();
    });

    it('should show yesterday label + HH:mm for yesterday', () => {
      const yesterday = new Date();
      yesterday.setDate(yesterday.getDate() - 1);
      yesterday.setHours(9, 15, 0, 0);
      const result = formatMessageTimestamp(yesterday, 'en', 'Yesterday');
      expect(result.label).toBe('Yesterday 09:15');
    });

    it('should show zh yesterday label', () => {
      const yesterday = new Date();
      yesterday.setDate(yesterday.getDate() - 1);
      yesterday.setHours(20, 0, 0, 0);
      const result = formatMessageTimestamp(yesterday, 'zh', '昨天');
      expect(result.label).toBe('昨天 20:00');
    });

    it('should show month+day for same year (en)', () => {
      const currentYear = new Date().getFullYear();
      const date = new Date(currentYear, 2, 15, 10, 45);
      const result = formatMessageTimestamp(date, 'en', 'Yesterday');
      expect(result.label).toMatch(/Mar 15, 10:45/);
    });

    it('should show M月d日 for same year (zh)', () => {
      const currentYear = new Date().getFullYear();
      const date = new Date(currentYear, 2, 15, 10, 45);
      const result = formatMessageTimestamp(date, 'zh', '昨天');
      expect(result.label).toBe('3月15日 10:45');
    });

    it('should show full date with year for different year (en)', () => {
      const date = new Date(2023, 11, 25, 18, 30);
      const result = formatMessageTimestamp(date, 'en', 'Yesterday');
      expect(result.label).toMatch(/Dec 25, 2023, 18:30/);
    });

    it('should show full date with year for different year (zh)', () => {
      const date = new Date(2023, 11, 25, 18, 30);
      const result = formatMessageTimestamp(date, 'zh', '昨天');
      expect(result.label).toBe('2023年12月25日 18:30');
    });

    it('should return empty strings for invalid date', () => {
      const result = formatMessageTimestamp('invalid-date', 'en', 'Yesterday');
      expect(result.label).toBe('');
      expect(result.title).toBe('');
    });

    it('should return empty strings for NaN timestamp', () => {
      const result = formatMessageTimestamp(NaN, 'en', 'Yesterday');
      expect(result.label).toBe('');
      expect(result.title).toBe('');
    });

    it('should accept number timestamp', () => {
      const now = Date.now();
      const result = formatMessageTimestamp(now, 'en', 'Yesterday');
      expect(result.label).toBeTruthy();
      expect(result.title).toBeTruthy();
    });

    it('should accept ISO string input', () => {
      const today = new Date();
      today.setHours(8, 0, 0, 0);
      const result = formatMessageTimestamp(today.toISOString(), 'en', 'Yesterday');
      expect(result.label).toBeTruthy();
    });

    it('should degrade gracefully for unknown locale without throwing', () => {
      const date = new Date(2023, 5, 10, 12, 0);
      // Intl 对未登记语言标签按运行时默认 locale 优雅降级，年份与 24 小时制时间恒存在
      const result = formatMessageTimestamp(date, 'xx', 'Hier');
      expect(result.label).toContain('2023');
      expect(result.label).toContain('12:00');
    });

    it('should generate hover title with full date info', () => {
      const now = new Date();
      now.setHours(14, 30, 0, 0);
      const result = formatMessageTimestamp(now, 'en', 'Yesterday');
      expect(result.title).toContain('30');
      expect(result.title.length).toBeGreaterThan(10);
    });

    it('should render full-precision hover titles per native locale hour cycle', () => {
      const date = new Date(2023, 11, 25, 18, 30, 45);
      expect(formatMessageTimestamp(date, 'en', 'Yesterday').title).toBe(
        'Monday, December 25, 2023 at 06:30:45 PM',
      );
      expect(formatMessageTimestamp(date, 'zh', '昨天').title).toBe('2023年12月25日星期一 18:30:45');
    });

    it('should work with ja locale for same year', () => {
      const currentYear = new Date().getFullYear();
      const date = new Date(currentYear, 0, 5, 9, 0);
      const result = formatMessageTimestamp(date, 'ja', '昨日');
      expect(result.label).toBeTruthy();
      expect(result.title).toBeTruthy();
    });
  });
});
