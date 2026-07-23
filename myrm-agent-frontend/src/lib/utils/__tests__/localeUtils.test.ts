import { describe, it, expect } from 'vitest';
import {
  negotiateLocale,
  normalizeLocaleForBackend,
  parseLocaleQueryParam,
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

    it('should keep ja as ja', () => {
      expect(normalizeLocaleForBackend('ja')).toBe('ja');
    });

    it('should keep ko as ko', () => {
      expect(normalizeLocaleForBackend('ko')).toBe('ko');
    });

    it('should keep de as de', () => {
      expect(normalizeLocaleForBackend('de')).toBe('de');
    });

    it('should return undefined for null input', () => {
      expect(normalizeLocaleForBackend(null)).toBeUndefined();
    });

    it('should pass through unmapped locales', () => {
      expect(normalizeLocaleForBackend('fr')).toBe('fr');
    });
  });

  describe('parseLocaleQueryParam', () => {
    it('accepts supported marketing locales', () => {
      expect(parseLocaleQueryParam('en')).toBe('en');
      expect(parseLocaleQueryParam('zh')).toBe('zh');
    });

    it('accepts other supported app locales', () => {
      expect(parseLocaleQueryParam('ja')).toBe('ja');
    });

    it('rejects unknown or empty values', () => {
      expect(parseLocaleQueryParam(null)).toBeNull();
      expect(parseLocaleQueryParam('')).toBeNull();
      expect(parseLocaleQueryParam('fr')).toBeNull();
    });
  });

  describe('urlWithoutLocaleParam', () => {
    it('removes locale while preserving redirect and utm params', () => {
      const source = new URL(
        'https://app.myrmagent.ai/auth/login?locale=en&redirect=%2Fpricing&utm_source=website',
      );
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
      expect(negotiateLocale('ja')).toBe('ja');
      expect(negotiateLocale('ko')).toBe('ko');
      expect(negotiateLocale('de')).toBe('de');
      expect(negotiateLocale('zh')).toBe('zh');
    });

    it('matches region variant to base locale', () => {
      expect(negotiateLocale('en-US')).toBe('en');
      expect(negotiateLocale('en-GB,en;q=0.9')).toBe('en');
      expect(negotiateLocale('ja-JP')).toBe('ja');
      expect(negotiateLocale('ko-KR')).toBe('ko');
      expect(negotiateLocale('de-DE')).toBe('de');
    });

    it('matches zh-TW exactly before falling back to zh', () => {
      expect(negotiateLocale('zh-TW')).toBe('zh-TW');
      expect(negotiateLocale('zh-CN')).toBe('zh');
      expect(negotiateLocale('zh-HK')).toBe('zh');
    });

    it('respects quality factor ordering', () => {
      expect(negotiateLocale('fr;q=0.8,ja;q=0.9,en;q=0.7')).toBe('ja');
      expect(negotiateLocale('ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7')).toBe('ko');
    });

    it('falls back to en for unsupported languages', () => {
      expect(negotiateLocale('fr-FR,fr;q=0.9')).toBe('en');
      expect(negotiateLocale('pt-BR')).toBe('en');
      expect(negotiateLocale('ar')).toBe('en');
    });

    it('falls back to en for null/undefined/empty', () => {
      expect(negotiateLocale(null)).toBe('en');
      expect(negotiateLocale(undefined)).toBe('en');
      expect(negotiateLocale('')).toBe('en');
    });

    it('skips wildcard entries', () => {
      expect(negotiateLocale('*;q=0.5,ja;q=0.9')).toBe('ja');
      expect(negotiateLocale('*')).toBe('en');
    });

    it('handles malformed quality factor gracefully', () => {
      expect(negotiateLocale('en;q=abc')).toBe('en');
      expect(negotiateLocale('ja;q=')).toBe('ja');
    });

    it('handles complex real-world Accept-Language headers', () => {
      expect(negotiateLocale('zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7')).toBe('zh-TW');
      expect(negotiateLocale('de-DE,de;q=0.9,en-US;q=0.8,en;q=0.7,ja;q=0.5')).toBe('de');
    });
  });
});
