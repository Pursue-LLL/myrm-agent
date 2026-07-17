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

export type StreamLocale = 'en' | 'zh' | 'ja' | 'ko' | 'de';

type NotificationCopy = {
  clarificationNeeded: string;
  desktopControlApprovalNeeded: string;
};

const localeLoaders: Record<StreamLocale, () => Promise<NotificationCopy>> = {
  en: () => import('../../../locales/namespaces/en/notifications.json').then((module) => module.default),
  zh: () => import('../../../locales/namespaces/zh/notifications.json').then((module) => module.default),
  ja: () => import('../../../locales/namespaces/ja/notifications.json').then((module) => module.default),
  ko: () => import('../../../locales/namespaces/ko/notifications.json').then((module) => module.default),
  de: () => import('../../../locales/namespaces/de/notifications.json').then((module) => module.default),
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

  const schedule =
    window.requestIdleCallback ??
    ((callback: () => void) => {
      window.setTimeout(callback, 1);
    });

  schedule(() => {
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
  if (lang.startsWith('zh')) return 'zh';
  if (lang.startsWith('ja')) return 'ja';
  if (lang.startsWith('ko')) return 'ko';
  if (lang.startsWith('de')) return 'de';
  return 'en';
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
