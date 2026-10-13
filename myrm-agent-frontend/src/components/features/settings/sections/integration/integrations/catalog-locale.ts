'use client';

/**
 * [INPUT] next-intl::useLocale (POS: 当前界面语言)
 * [OUTPUT] CatalogLocale: 目录文案语种（zh / en）; toCatalogLocale: 界面语言到目录语种的映射; useCatalogLocale: 当前界面对应的目录语种
 * [POS] 集成目录的文案语种选择。目录条目只提供中英文两套文案，目录页、连接对话框与引导页共用同一映射。
 */
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
