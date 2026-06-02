import { isToday, isYesterday, format } from 'date-fns';
import { zhCN, enUS, ja, ko, de } from 'date-fns/locale';

const DATE_FNS_LOCALES: Record<string, import('date-fns').Locale> = {
  zh: zhCN,
  en: enUS,
  ja,
  ko,
  de,
};

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
 * 将两个日期之间的时间差格式化为人类可读的字符串。
 */
export const formatTimeDifference = (date1: Date | string, date2: Date | string): string => {
  const d1 = date1 instanceof Date ? date1 : new Date(date1);
  const d2 = date2 instanceof Date ? date2 : new Date(date2);

  const diffInSeconds = Math.floor(Math.abs(d2.getTime() - d1.getTime()) / 1000);

  const SECONDS_IN_MINUTE = 60;
  const SECONDS_IN_HOUR = 3600;
  const SECONDS_IN_DAY = 86400;
  const SECONDS_IN_YEAR = 31536000;

  if (diffInSeconds < SECONDS_IN_MINUTE) {
    return `${diffInSeconds} second${diffInSeconds !== 1 ? 's' : ''}`;
  }

  const minutes = Math.floor(diffInSeconds / SECONDS_IN_MINUTE);
  if (diffInSeconds < SECONDS_IN_HOUR) {
    return `${minutes} minute${minutes !== 1 ? 's' : ''}`;
  }

  const hours = Math.floor(diffInSeconds / SECONDS_IN_HOUR);
  if (diffInSeconds < SECONDS_IN_DAY) {
    return `${hours} hour${hours !== 1 ? 's' : ''}`;
  }

  const days = Math.floor(diffInSeconds / SECONDS_IN_DAY);
  if (diffInSeconds < SECONDS_IN_YEAR) {
    return `${days} day${days !== 1 ? 's' : ''}`;
  }

  const years = Math.floor(diffInSeconds / SECONDS_IN_YEAR);
  return `${years} year${years !== 1 ? 's' : ''}`;
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

  const loc = DATE_FNS_LOCALES[locale] ?? enUS;

  let label: string;
  if (isToday(d)) {
    label = format(d, 'HH:mm', { locale: loc });
  } else if (isYesterday(d)) {
    label = `${yesterdayLabel} ${format(d, 'HH:mm', { locale: loc })}`;
  } else if (d.getFullYear() === new Date().getFullYear()) {
    label = locale === 'zh' ? format(d, 'M月d日 HH:mm', { locale: loc }) : format(d, 'MMM d, HH:mm', { locale: loc });
  } else {
    label =
      locale === 'zh'
        ? format(d, 'yyyy年M月d日 HH:mm', { locale: loc })
        : format(d, 'MMM d, yyyy HH:mm', { locale: loc });
  }

  const title = d.toLocaleString(locale === 'zh' ? 'zh-CN' : locale, {
    weekday: 'long',
    year: 'numeric',
    month: 'long',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  });

  return { label, title };
};
