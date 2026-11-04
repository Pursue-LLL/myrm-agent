/**
 * [INPUT]
 * - Intl.DateTimeFormat (built-in): locale-aware weekday names
 *
 * [OUTPUT]
 * - weekdayLabels: short weekday names for a locale, Monday first
 *
 * [POS]
 * Statistics charts index weekdays 0-6 starting on Monday (the server's day-of-week numbering). The names come from
 * the runtime's locale data, so every supported language gets its own without a hand-kept list per language.
 */

/** 2024-01-01 is a Monday. */
const MONDAY_UTC = Date.UTC(2024, 0, 1);
const DAY_MS = 24 * 60 * 60 * 1000;

export function weekdayLabels(locale: string): string[] {
  const format = new Intl.DateTimeFormat(locale, { weekday: 'short', timeZone: 'UTC' });
  return Array.from({ length: 7 }, (_, index) => format.format(new Date(MONDAY_UTC + index * DAY_MS)));
}
