/**
 * [INPUT]
 * #locales/*.json::notifications.clarificationNeeded (POS: OS notification copy SSOT)
 *
 * [OUTPUT]
 * resolveStreamLocale, getClarificationNotificationTitle, preloadNotificationCopy
 *
 * [POS]
 * Locale strings for stream handlers that cannot use next-intl hooks.
 * Loads notification slices on idle to avoid bundling all locale JSON upfront.
 */

import { scheduleWhenIdle } from '@/lib/utils/scheduleWhenIdle';

export type StreamLocale = 'en' | 'zh';

type NotificationCopy = {
  clarificationNeeded: string;
  desktopControlApprovalNeeded: string;
};

function toNotificationCopy(module: Record<string, unknown>): NotificationCopy {
  return {
    clarificationNeeded:
      typeof module.clarificationNeeded === 'string' ? module.clarificationNeeded : 'Agent needs your input',
    desktopControlApprovalNeeded:
      typeof module.desktopControlApprovalNeeded === 'string'
        ? module.desktopControlApprovalNeeded
        : 'Desktop control approval required',
  };
}

const localeLoaders: Record<StreamLocale, () => Promise<NotificationCopy>> = {
  en: () =>
    import('../../../locales/namespaces/en/notifications.json').then((module) => toNotificationCopy(module.default)),
  zh: () =>
    import('../../../locales/namespaces/zh/notifications.json').then((module) => toNotificationCopy(module.default)),
};

const notificationCache: Partial<Record<StreamLocale, NotificationCopy>> = {};

const FALLBACK_COPY: NotificationCopy = {
  clarificationNeeded: 'Agent needs your input',
  desktopControlApprovalNeeded: 'Desktop control approval required',
};

export async function preloadNotificationCopy(): Promise<void> {
  await Promise.all(
    (Object.keys(localeLoaders) as StreamLocale[]).map(async (locale) => {
      notificationCache[locale] = await localeLoaders[locale]();
    }),
  );
}

function scheduleNotificationCopyWarmup(): void {
  if (typeof window === 'undefined') {
    return;
  }

  scheduleWhenIdle(() => {
    void preloadNotificationCopy();
  });
}

scheduleNotificationCopyWarmup();

void localeLoaders.en().then((copy) => {
  notificationCache.en = copy;
});

void localeLoaders.zh().then((copy) => {
  notificationCache.zh = copy;
});

export function resolveStreamLocale(lang: string): StreamLocale {
  return lang.startsWith('zh') ? 'zh' : 'en';
}

export function getClarificationNotificationTitle(lang: string): string {
  const locale = resolveStreamLocale(lang);
  return (
    notificationCache[locale]?.clarificationNeeded ??
    notificationCache.en?.clarificationNeeded ??
    FALLBACK_COPY.clarificationNeeded
  );
}

export function getDesktopControlApprovalNotificationTitle(lang: string): string {
  const locale = resolveStreamLocale(lang);
  return (
    notificationCache[locale]?.desktopControlApprovalNeeded ??
    notificationCache.en?.desktopControlApprovalNeeded ??
    FALLBACK_COPY.desktopControlApprovalNeeded
  );
}
