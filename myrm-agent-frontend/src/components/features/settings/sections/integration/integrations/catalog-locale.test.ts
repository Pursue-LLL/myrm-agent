import { renderHook } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { toCatalogLocale, useCatalogLocale } from './catalog-locale';

const uiLocale = vi.hoisted(() => ({ current: 'en' }));

vi.mock('next-intl', () => ({
  useLocale: () => uiLocale.current,
}));

describe('toCatalogLocale', () => {
  it.each(['zh', 'zh-CN', 'zh-TW'])('maps the Chinese variant %s to the Chinese catalog copy', (locale) => {
    expect(toCatalogLocale(locale)).toBe('zh');
  });

  it.each(['en', 'ja', 'ko', 'de'])('maps %s to the English catalog copy', (locale) => {
    expect(toCatalogLocale(locale)).toBe('en');
  });
});

describe('useCatalogLocale', () => {
  it('follows the active UI locale', () => {
    uiLocale.current = 'zh-TW';
    expect(renderHook(() => useCatalogLocale()).result.current).toBe('zh');

    uiLocale.current = 'ja';
    expect(renderHook(() => useCatalogLocale()).result.current).toBe('en');
  });
});
