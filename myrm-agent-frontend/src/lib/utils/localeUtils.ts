/**
 * Client-side locale detection utility
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
    if (name === 'NEXT_LOCALE') {
      return value;
    }
  }

  return null;
}

/**
 * Normalize locale to backend format
 * Frontend uses: 'zh', 'en', 'ja', 'ko', 'de'
 * Backend expects: 'zh-CN', 'en', 'ja', 'ko', 'de', etc.
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
  };

  return mapping[frontendLocale] || frontendLocale;
}
