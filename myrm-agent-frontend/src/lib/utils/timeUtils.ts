/**
 * [POS]
 * Wall-clock time helpers: compact run durations (mirroring the backend
 * `_format_duration`), IANA timezone, unix seconds, and locale-aware
 * message timestamp labels via Intl.DateTimeFormat (all six app locales
 * natively; hourCycle h23 for the 24-hour clock).
 *
 * [OUTPUT]
 * - formatDuration
 * - getUserTimezone
 * - getCurrentTimestamp
 * - formatMessageTimestamp
 */

type TimestampVariant = 'time' | 'monthday' | 'fulldate' | 'title';

// Message lists render a label per message; reuse immutable formatters
// instead of reallocating per row (same pattern as relativeTime.ts).
// Row labels keep the 24-hour clock; the hover title follows each locale's
// native hour convention (en 12h / zh 24h), matching full-precision wording.
const VARIANT_OPTIONS: Record<TimestampVariant, Intl.DateTimeFormatOptions> = {
  time: { hour: '2-digit', minute: '2-digit', hourCycle: 'h23' },
  monthday: { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', hourCycle: 'h23' },
  fulldate: { year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', hourCycle: 'h23' },
  title: {
    weekday: 'long',
    year: 'numeric',
    month: 'long',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  },
};

const tsFormatterCache = new Map<string, Intl.DateTimeFormat>();

function getTsFormatter(variant: TimestampVariant, locale: string): Intl.DateTimeFormat {
  const key = `${variant}|${locale}`;
  let formatter = tsFormatterCache.get(key);
  if (formatter === undefined) {
    formatter = new Intl.DateTimeFormat(locale, VARIANT_OPTIONS[variant]);
    tsFormatterCache.set(key, formatter);
  }
  return formatter;
}

function isSameCalendarDay(a: Date, b: Date): boolean {
  return a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate();
}

/**
 * Format a wall-clock duration compactly: 42s / 8m 30s / 1h 5m.
 *
 * Mirrors the backend `_format_duration` so notification and detail-page
 * wording stay consistent across surfaces. Returns "—" when the two ISO
 * timestamps are missing or invalid.
 */
export function formatDuration(startIso: string | null | undefined, endIso: string | null | undefined): string {
  if (!startIso || !endIso) {
    return '—';
  }
  const start = new Date(startIso).getTime();
  const end = new Date(endIso).getTime();
  if (Number.isNaN(start) || Number.isNaN(end) || end < start) {
    return '—';
  }
  const totalSeconds = Math.max(0, Math.floor((end - start) / 1000));
  if (totalSeconds < 60) {
    return `${totalSeconds}s`;
  }
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  if (minutes < 60) {
    return seconds === 0 ? `${minutes}m` : `${minutes}m ${seconds}s`;
  }
  const hours = Math.floor(minutes / 60);
  const remMinutes = minutes % 60;
  return remMinutes === 0 ? `${hours}h` : `${hours}h ${remMinutes}m`;
}

/**
 * Get the user's current IANA timezone.
 *
 * @returns IANA timezone string (e.g., "Asia/Shanghai", "America/New_York").
 */
export const getUserTimezone = (): string => {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone;
  } catch {
    return 'UTC';
  }
};

/**
 * Get the current timestamp in seconds (Unix timestamp as float).
 *
 * @returns Current timestamp in seconds (float).
 */
export const getCurrentTimestamp = (): number => {
  return Date.now() / 1000;
};

/**
 * 格式化消息时间戳为智能显示格式。
 *
 * @returns {{ label: string; title: string }} label 为简短显示，title 为 hover 完整时间。
 */
export const formatMessageTimestamp = (
  date: Date | string | number,
  locale: string,
  yesterdayLabel: string,
): { label: string; title: string } => {
  const d = date instanceof Date ? date : new Date(date);
  if (!Number.isFinite(d.getTime())) {
    return { label: '', title: '' };
  }

  const now = new Date();
  const yesterday = new Date(now);
  yesterday.setDate(now.getDate() - 1);

  let label: string;
  if (isSameCalendarDay(d, now)) {
    label = getTsFormatter('time', locale).format(d);
  } else if (isSameCalendarDay(d, yesterday)) {
    label = `${yesterdayLabel} ${getTsFormatter('time', locale).format(d)}`;
  } else if (d.getFullYear() === now.getFullYear()) {
    label = getTsFormatter('monthday', locale).format(d);
  } else {
    label = getTsFormatter('fulldate', locale).format(d);
  }

  const title = getTsFormatter('title', locale).format(d);

  return { label, title };
};
