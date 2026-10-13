'use client';

import { useLocale } from 'next-intl';

/** The catalog ships Chinese and English copy; every other UI language reads the English copy. */
export type CatalogLocale = 'zh' | 'en';

/** Chinese variants (zh, zh-TW, ...) share the Chinese catalog copy. */
export function toCatalogLocale(locale: string): CatalogLocale {
  return locale.startsWith('zh') ? 'zh' : 'en';
}

export function useCatalogLocale(): CatalogLocale {
  return toCatalogLocale(useLocale());
}
