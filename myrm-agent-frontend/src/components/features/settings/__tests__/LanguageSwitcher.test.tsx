import { describe, it, expect } from 'vitest';
import { normalizeLocaleForBackend } from '@/lib/utils/localeUtils';

/**
 * Test LanguageSwitcher personalSettings update logic
 * Logic: when language changes, update personalSettings with normalized locale
 */
describe('LanguageSwitcher - personalSettings update logic', () => {
  it('should normalize zh to zh-CN when updating personalSettings', () => {
    // Simulate handleLanguageChange logic
    const newLocale = 'zh';
    const backendLocale = normalizeLocaleForBackend(newLocale);

    expect(backendLocale).toBe('zh-CN');
  });

  it('should keep en as-is when updating personalSettings', () => {
    const newLocale = 'en';
    const backendLocale = normalizeLocaleForBackend(newLocale);

    expect(backendLocale).toBe('en');
  });

  it('should keep ja as-is when updating personalSettings', () => {
    const newLocale = 'ja';
    const backendLocale = normalizeLocaleForBackend(newLocale);

    expect(backendLocale).toBe('ja');
  });

  it('should keep ko as-is when updating personalSettings', () => {
    const newLocale = 'ko';
    const backendLocale = normalizeLocaleForBackend(newLocale);

    expect(backendLocale).toBe('ko');
  });

  it('should keep de as-is when updating personalSettings', () => {
    const newLocale = 'de';
    const backendLocale = normalizeLocaleForBackend(newLocale);

    expect(backendLocale).toBe('de');
  });

  it('should handle unmapped locales', () => {
    const newLocale = 'fr';
    const backendLocale = normalizeLocaleForBackend(newLocale);

    expect(backendLocale).toBe('fr'); // pass through
  });
});
