/**
 * [INPUT]
 * - Intl.DateTimeFormat (built-in): locale-aware date and time rendering
 *
 * [OUTPUT]
 * - formatBytes: binary-unit size label
 * - formatBackupDate: locale-aware date and time of when a backup was made
 *
 * [POS]
 * Size and date labels for backup files and transfers.
 */

const UNITS = ['B', 'KB', 'MB', 'GB', 'TB'] as const;

export function formatBytes(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes <= 0) {
    return '0 B';
  }
  const index = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), UNITS.length - 1);
  const value = bytes / 1024 ** index;
  return `${index === 0 ? value : value.toFixed(value >= 100 ? 0 : 1)} ${UNITS[index]}`;
}

export function formatBackupDate(iso: string, locale: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) {
    return '';
  }
  return new Intl.DateTimeFormat(locale, { dateStyle: 'medium', timeStyle: 'short' }).format(date);
}
