import { describe, it, expect, vi } from 'vitest';
import { getUserTimezone, getCurrentTimestamp, formatTimeDifference, formatMessageTimestamp } from '../timeUtils';

describe('timeUtils', () => {
  describe('getUserTimezone', () => {
    it('should return IANA timezone string', () => {
      const timezone = getUserTimezone();
      expect(typeof timezone).toBe('string');
      expect(timezone.length).toBeGreaterThan(0);
    });

    it('should fallback to UTC when Intl API throws', () => {
      vi.spyOn(Intl, 'DateTimeFormat').mockImplementationOnce(() => {
        throw new Error('Intl error');
      });

      expect(getUserTimezone()).toBe('UTC');
      vi.restoreAllMocks();
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

  describe('formatTimeDifference', () => {
    it('should format seconds correctly', () => {
      const date1 = new Date('2024-01-01T00:00:00Z');
      const date2 = new Date('2024-01-01T00:00:30Z');

      expect(formatTimeDifference(date1, date2)).toBe('30 seconds');
    });

    it('should format single second correctly', () => {
      const date1 = new Date('2024-01-01T00:00:00Z');
      const date2 = new Date('2024-01-01T00:00:01Z');

      expect(formatTimeDifference(date1, date2)).toBe('1 second');
    });

    it('should format minutes correctly', () => {
      const date1 = new Date('2024-01-01T00:00:00Z');
      const date2 = new Date('2024-01-01T00:05:00Z');

      expect(formatTimeDifference(date1, date2)).toBe('5 minutes');
    });

    it('should format single minute correctly', () => {
      const date1 = new Date('2024-01-01T00:00:00Z');
      const date2 = new Date('2024-01-01T00:01:00Z');

      expect(formatTimeDifference(date1, date2)).toBe('1 minute');
    });

    it('should format hours correctly', () => {
      const date1 = new Date('2024-01-01T00:00:00Z');
      const date2 = new Date('2024-01-01T03:00:00Z');

      expect(formatTimeDifference(date1, date2)).toBe('3 hours');
    });

    it('should format single hour correctly', () => {
      const date1 = new Date('2024-01-01T00:00:00Z');
      const date2 = new Date('2024-01-01T01:00:00Z');

      expect(formatTimeDifference(date1, date2)).toBe('1 hour');
    });

    it('should format days correctly', () => {
      const date1 = new Date('2024-01-01T00:00:00Z');
      const date2 = new Date('2024-01-04T00:00:00Z');

      expect(formatTimeDifference(date1, date2)).toBe('3 days');
    });

    it('should format single day correctly', () => {
      const date1 = new Date('2024-01-01T00:00:00Z');
      const date2 = new Date('2024-01-02T00:00:00Z');

      expect(formatTimeDifference(date1, date2)).toBe('1 day');
    });

    it('should format years correctly', () => {
      const date1 = new Date('2024-01-01T00:00:00Z');
      const date2 = new Date('2026-01-01T00:00:00Z');

      expect(formatTimeDifference(date1, date2)).toBe('2 years');
    });

    it('should format single year correctly', () => {
      const date1 = new Date('2024-01-01T00:00:00Z');
      const date2 = new Date('2025-01-01T00:00:00Z');

      expect(formatTimeDifference(date1, date2)).toBe('1 year');
    });

    it('should work with string dates', () => {
      const result = formatTimeDifference('2024-01-01T00:00:00Z', '2024-01-01T00:00:45Z');
      expect(result).toBe('45 seconds');
    });

    it('should handle reversed date order', () => {
      const date1 = new Date('2024-01-01T00:05:00Z');
      const date2 = new Date('2024-01-01T00:00:00Z');

      expect(formatTimeDifference(date1, date2)).toBe('5 minutes');
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
      expect(result.label).toMatch(/Dec 25, 2023 18:30/);
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

    it('should fallback to enUS for unknown locale', () => {
      const date = new Date(2023, 5, 10, 12, 0);
      const result = formatMessageTimestamp(date, 'fr', 'Hier');
      expect(result.label).toMatch(/Jun 10, 2023 12:00/);
    });

    it('should generate hover title with full date info', () => {
      const now = new Date();
      now.setHours(14, 30, 0, 0);
      const result = formatMessageTimestamp(now, 'en', 'Yesterday');
      expect(result.title).toContain('30');
      expect(result.title.length).toBeGreaterThan(10);
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
