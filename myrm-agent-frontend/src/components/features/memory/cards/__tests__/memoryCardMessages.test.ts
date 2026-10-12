import { describe, expect, it, vi } from 'vitest';

import de from '../../../../../../locales/de.json';
import en from '../../../../../../locales/en.json';
import ja from '../../../../../../locales/ja.json';
import ko from '../../../../../../locales/ko.json';
import zhTW from '../../../../../../locales/zh-TW.json';
import zh from '../../../../../../locales/zh.json';

// The global test setup replaces next-intl, so the real formatter is loaded explicitly.
const { createTranslator } = await vi.importActual<typeof import('next-intl')>('next-intl');

const locales = { en, zh, 'zh-TW': zhTW, ja, ko, de } as const;

const CARD_MESSAGE_KEYS = [
  'locked',
  'exactFact',
  'exactFactHint',
  'usedTimes',
  'lastUsedAt',
  'fields.reasoning',
  'fields.application',
  'conflict.lowRiskPolicyHint',
  'conflict.chatBannerTitle',
  'conflict.chatBannerAction',
  'conflict.chatBannerDismiss',
  'conflict.fetchRefreshFailed',
  'targetChangedTitle',
  'targetChangedDesc',
  'batchApprovePartialDesc',
] as const;

const translatorFor = (locale: keyof typeof locales) =>
  createTranslator({ locale, messages: locales[locale], namespace: 'memory' });

describe('memory card messages', () => {
  it.each(Object.keys(locales) as (keyof typeof locales)[])('%s defines every card message key', (locale) => {
    const t = translatorFor(locale);

    for (const key of CARD_MESSAGE_KEYS) {
      const message = t(key, { count: 2, time: 'noon', hours: 24, success: 3, failed: 4 });
      expect(message, `${locale}:${key}`).not.toBe(`memory.${key}`);
      expect(message.length).toBeGreaterThan(0);
    }
  });

  it('uses the singular form for a single use in English', () => {
    const t = translatorFor('en');

    expect(t('usedTimes', { count: 1 })).toBe('Used 1 time');
    expect(t('usedTimes', { count: 7 })).toBe('Used 7 times');
  });

  it('pluralizes the conflict banner title where the language distinguishes one from many', () => {
    expect(translatorFor('en')('conflict.chatBannerTitle', { count: 1 })).toBe('One memory conflict needs your review');
    expect(translatorFor('en')('conflict.chatBannerTitle', { count: 3 })).toBe('3 memory conflicts need your review');
    expect(translatorFor('de')('conflict.chatBannerTitle', { count: 1 })).toMatch(/^Ein /);
    expect(translatorFor('de')('conflict.chatBannerTitle', { count: 3 })).toMatch(/^3 /);
  });

  it('keeps the count in the conflict banner title of every locale', () => {
    for (const locale of Object.keys(locales) as (keyof typeof locales)[]) {
      expect(translatorFor(locale)('conflict.chatBannerTitle', { count: 3 }), locale).toContain('3');
    }
  });

  it('interpolates the count and time in every locale', () => {
    for (const locale of Object.keys(locales) as (keyof typeof locales)[]) {
      const t = translatorFor(locale);

      expect(t('usedTimes', { count: 7 }), locale).toContain('7');
      expect(t('lastUsedAt', { time: 'noon' }), locale).toContain('noon');
    }
  });

  it('keeps both batch approval counts in every locale', () => {
    for (const locale of Object.keys(locales) as (keyof typeof locales)[]) {
      const message = translatorFor(locale)('batchApprovePartialDesc', { success: 3, failed: 4 });

      expect(message, locale).toContain('3');
      expect(message, locale).toContain('4');
    }
  });
});
