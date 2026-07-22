import { type Locale, locales } from '@/i18n/config';

/** next-intl locale cookie — shared by middleware relay and `i18n/index.ts`. */
export const NEXT_LOCALE_COOKIE_NAME = 'NEXT_LOCALE';

/**
 * Locale utilities for client hooks, middleware marketing relay, and backend normalization.
 */

/**
 * Get current user locale from cookie
 * This works in client components
 */
export function getClientLocale(): string | null {
  if (typeof document === 'undefined') {
    return null;
  }

  // Read NEXT_LOCALE cookie (set by next-intl)
  const cookies = document.cookie.split(';');
  for (const cookie of cookies) {
    const [name, value] = cookie.trim().split('=');
    if (name === NEXT_LOCALE_COOKIE_NAME) {
      return value;
    }
  }

  return null;
}

/**
 * Normalize locale to backend format
 * Frontend uses: 'zh', 'en', 'ja', 'ko', 'de', 'zh-TW'
 * Backend expects: 'zh-CN', 'en', 'ja', 'ko', 'de', 'zh-TW', etc.
 */
export function normalizeLocaleForBackend(frontendLocale: string | null): string | undefined {
  if (!frontendLocale) {
    return undefined;
  }

  // Map frontend locales to backend format
  const mapping: Record<string, string> = {
    zh: 'zh-CN',
    en: 'en',
    ja: 'ja',
    ko: 'ko',
    de: 'de',
    'zh-TW': 'zh-TW',
  };

  return mapping[frontendLocale] || frontendLocale;
}

/** Parse `?locale=` from marketing-site CTAs into a supported App locale. */
export function parseLocaleQueryParam(value: string | null): Locale | null {
  if (!value) return null;
  return (locales as readonly string[]).includes(value) ? (value as Locale) : null;
}

/** Clone URL without `locale` search param (preserves redirect, token, utm, etc.). */
export function urlWithoutLocaleParam(url: URL): URL {
  const next = new URL(url.toString());
  next.searchParams.delete('locale');
  return next;
}
