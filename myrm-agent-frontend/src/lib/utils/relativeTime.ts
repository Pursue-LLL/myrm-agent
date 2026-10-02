/**
 * [POS]
 * Locale-aware relative time formatting via Intl.RelativeTimeFormat
 * (auto "just now"/"x minutes ago" phrasing; all six app locales supported natively).
 */

export function formatRelativeTime(isoTimestamp: string, locale: string): string {
  const then = new Date(isoTimestamp).getTime();
  if (Number.isNaN(then)) {
    return '';
  }
  const diffSeconds = Math.round((then - Date.now()) / 1000);
  const absSeconds = Math.abs(diffSeconds);
  const formatter = new Intl.RelativeTimeFormat(locale, { numeric: 'auto' });
  if (absSeconds < 60) {
    return formatter.format(diffSeconds, 'second');
  }
  if (absSeconds < 3600) {
    return formatter.format(Math.round(diffSeconds / 60), 'minute');
  }
  if (absSeconds < 86400) {
    return formatter.format(Math.round(diffSeconds / 3600), 'hour');
  }
  return formatter.format(Math.round(diffSeconds / 86400), 'day');
}
