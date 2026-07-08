/**
 * [INPUT]
 * #locales/*.json::notifications.clarificationNeeded (POS: OS notification copy SSOT)
 *
 * [OUTPUT]
 * resolveStreamLocale, getClarificationNotificationTitle: non-React SSE handler i18n helpers
 *
 * [POS]
 * Locale strings for stream handlers that cannot use next-intl hooks.
 */

import deMessages from '#locales/de.json';
import enMessages from '#locales/en.json';
import jaMessages from '#locales/ja.json';
import koMessages from '#locales/ko.json';
import zhMessages from '#locales/zh.json';

export type StreamLocale = 'en' | 'zh' | 'ja' | 'ko' | 'de';

const NOTIFICATION_COPY: Record<StreamLocale, { clarificationNeeded: string }> = {
  en: enMessages.notifications,
  zh: zhMessages.notifications,
  ja: jaMessages.notifications,
  ko: koMessages.notifications,
  de: deMessages.notifications,
};

export function resolveStreamLocale(lang: string): StreamLocale {
  if (lang.startsWith('zh')) return 'zh';
  if (lang.startsWith('ja')) return 'ja';
  if (lang.startsWith('ko')) return 'ko';
  if (lang.startsWith('de')) return 'de';
  return 'en';
}

export function getClarificationNotificationTitle(lang: string): string {
  return NOTIFICATION_COPY[resolveStreamLocale(lang)].clarificationNeeded;
}
