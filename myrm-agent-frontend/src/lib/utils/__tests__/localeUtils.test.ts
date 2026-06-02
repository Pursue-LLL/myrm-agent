import { describe, it, expect } from 'vitest';
import { normalizeLocaleForBackend } from '../localeUtils';

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
});
