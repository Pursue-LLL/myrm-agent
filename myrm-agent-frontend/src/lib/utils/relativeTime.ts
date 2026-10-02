/**
 * [POS]
 * Locale-aware relative time formatting via Intl.RelativeTimeFormat
 * (auto "just now"/"x minutes ago" phrasing; all six app locales supported natively).
 *
 * [OUTPUT]
 * - formatRelativeTime
 */

const rtfCache = new Map<string, Intl.RelativeTimeFormat>();

function getFormatter(locale: string): Intl.RelativeTimeFormat {
  // Hub polls every 5s and renders up to 10 cards per pass; formatters are
  // immutable per locale, so reuse one instance instead of reallocating.
  let formatter = rtfCache.get(locale);
  if (formatter === undefined) {
    formatter = new Intl.RelativeTimeFormat(locale, { numeric: 'auto' });
    rtfCache.set(locale, formatter);
  }
  return formatter;
}

export function formatRelativeTime(isoTimestamp: string, locale: string): string {
  const then = new Date(isoTimestamp).getTime();
  if (Number.isNaN(then)) {
    return '';
  }
  const diffSeconds = Math.round((then - Date.now()) / 1000);
  const absSeconds = Math.abs(diffSeconds);
  const formatter = getFormatter(locale);
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
