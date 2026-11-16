import { describe, it, expect } from 'vitest';
import {
  negotiateLocale,
  normalizeLocaleForBackend,
  parseLocaleQueryParam,
  resolveBackendLocale,
  urlWithoutLocaleParam,
} from '../localeUtils';

describe('localeUtils', () => {
  describe('normalizeLocaleForBackend', () => {
    it('should normalize zh to zh-CN', () => {
      expect(normalizeLocaleForBackend('zh')).toBe('zh-CN');
    });

    it('should keep en as en', () => {
      expect(normalizeLocaleForBackend('en')).toBe('en');
    });

    it('should return undefined for empty input', () => {
      expect(normalizeLocaleForBackend(null)).toBeUndefined();
      expect(normalizeLocaleForBackend(undefined)).toBeUndefined();
      expect(normalizeLocaleForBackend('')).toBeUndefined();
    });

    it.each([
      ['zh-CN', 'zh-CN'],
      ['zh-TW', 'zh-CN'],
      ['zh_Hant', 'zh-CN'],
      ['en-US', 'en'],
      ['EN', 'en'],
    ])('should map the regional tag %s to the offered locale (%s)', (tag, expected) => {
      expect(normalizeLocaleForBackend(tag)).toBe(expected);
    });

    it.each(['ja', 'ko', 'de', 'fr', 'ja-JP'])(
      'should map the language %s the app does not offer to undefined',
      (tag) => {
        expect(normalizeLocaleForBackend(tag)).toBeUndefined();
      },
    );
  });

  describe('resolveBackendLocale', () => {
    it('prefers the saved locale over the cookie', () => {
      expect(resolveBackendLocale('zh-CN', 'en')).toBe('zh-CN');
      expect(resolveBackendLocale('en', 'zh')).toBe('en');
    });

    it('falls back to the cookie when nothing is saved', () => {
      expect(resolveBackendLocale(undefined, 'en')).toBe('en');
      expect(resolveBackendLocale(null, 'zh')).toBe('zh-CN');
      expect(resolveBackendLocale('', 'en')).toBe('en');
    });

    it.each(['ja', 'ko', 'de'])(
      'follows the interface language when the saved locale is the unsupported %s',
      (unsupported) => {
        expect(resolveBackendLocale(unsupported, 'zh')).toBe('zh-CN');
        expect(resolveBackendLocale(unsupported, 'en')).toBe('en');
      },
    );

    it('is undefined when neither source names an offered locale', () => {
      expect(resolveBackendLocale(undefined, null)).toBeUndefined();
      expect(resolveBackendLocale('ja', 'ko')).toBeUndefined();
    });
  });

  describe('parseLocaleQueryParam', () => {
    it('accepts supported marketing locales', () => {
      expect(parseLocaleQueryParam('en')).toBe('en');
      expect(parseLocaleQueryParam('zh')).toBe('zh');
    });

    it('rejects unknown or empty values', () => {
      expect(parseLocaleQueryParam(null)).toBeNull();
      expect(parseLocaleQueryParam('')).toBeNull();
      expect(parseLocaleQueryParam('fr')).toBeNull();
      expect(parseLocaleQueryParam('ja')).toBeNull();
      expect(parseLocaleQueryParam('zh-TW')).toBeNull();
    });
  });

  describe('urlWithoutLocaleParam', () => {
    it('removes locale while preserving redirect and utm params', () => {
      const source = new URL('https://app.myrmagent.ai/auth/login?locale=en&redirect=%2Fpricing&utm_source=website');
      const cleaned = urlWithoutLocaleParam(source);
      expect(cleaned.searchParams.get('locale')).toBeNull();
      expect(cleaned.searchParams.get('redirect')).toBe('/pricing');
      expect(cleaned.searchParams.get('utm_source')).toBe('website');
    });

    it('clears search when locale was the only param', () => {
      const source = new URL('https://app.myrmagent.ai/pricing?locale=zh');
      const cleaned = urlWithoutLocaleParam(source);
      expect(cleaned.search).toBe('');
    });
  });

  describe('negotiateLocale', () => {
    it('returns exact match for simple header', () => {
      expect(negotiateLocale('en')).toBe('en');
      expect(negotiateLocale('zh')).toBe('zh');
    });

    it('matches region variant to base locale', () => {
      expect(negotiateLocale('en-US')).toBe('en');
      expect(negotiateLocale('en-GB,en;q=0.9')).toBe('en');
      expect(negotiateLocale('zh-CN')).toBe('zh');
    });

    it('maps every Chinese variant to zh', () => {
      expect(negotiateLocale('zh-TW')).toBe('zh');
      expect(negotiateLocale('zh-HK')).toBe('zh');
      expect(negotiateLocale('zh-Hant')).toBe('zh');
    });

    it('respects quality factor ordering', () => {
      expect(negotiateLocale('fr;q=0.8,zh;q=0.9,en;q=0.7')).toBe('zh');
      expect(negotiateLocale('en;q=0.5,zh;q=0.9')).toBe('zh');
    });

    it('skips languages the app does not offer and takes the next supported one', () => {
      expect(negotiateLocale('ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7')).toBe('en');
      expect(negotiateLocale('ja-JP,ja;q=0.9,zh;q=0.8')).toBe('zh');
    });

    it('falls back to en for unsupported languages', () => {
      expect(negotiateLocale('fr-FR,fr;q=0.9')).toBe('en');
      expect(negotiateLocale('pt-BR')).toBe('en');
      expect(negotiateLocale('ja')).toBe('en');
      expect(negotiateLocale('de-DE')).toBe('en');
      expect(negotiateLocale('ar')).toBe('en');
    });

    it('falls back to en for null/undefined/empty', () => {
      expect(negotiateLocale(null)).toBe('en');
      expect(negotiateLocale(undefined)).toBe('en');
      expect(negotiateLocale('')).toBe('en');
    });

    it('skips wildcard entries', () => {
      expect(negotiateLocale('*;q=0.5,zh;q=0.9')).toBe('zh');
      expect(negotiateLocale('*')).toBe('en');
    });

    it('handles malformed quality factor gracefully', () => {
      expect(negotiateLocale('en;q=abc')).toBe('en');
      expect(negotiateLocale('zh;q=')).toBe('zh');
    });

    it('handles complex real-world Accept-Language headers', () => {
      expect(negotiateLocale('zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7')).toBe('zh');
      expect(negotiateLocale('de-DE,de;q=0.9,en-US;q=0.8,en;q=0.7,ja;q=0.5')).toBe('en');
    });
  });
});
