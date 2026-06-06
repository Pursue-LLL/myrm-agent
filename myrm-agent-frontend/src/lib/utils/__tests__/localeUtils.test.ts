import { describe, it, expect } from 'vitest';
import {
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
});
