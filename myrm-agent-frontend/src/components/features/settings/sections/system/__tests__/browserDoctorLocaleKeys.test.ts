/**
 * [INPUT]
 * locales/{zh,en}.json — `settings.browserDoctor` strings.
 * [OUTPUT]
 * Vitest: the diagnostics card block has identical keys and placeholders in every locale, and
 * every message the card can render formats with the real next-intl ICU formatter.
 * [POS]
 * Regression guard against raw i18n keys and broken ICU syntax on the browser diagnostics card.
 */

import { describe, expect, it, vi } from 'vitest';

import en from '../../../../../../../locales/en.json';
import zh from '../../../../../../../locales/zh.json';
import { DOCTOR_HINT_KEYS } from '../browserDoctorView';

// The global test setup replaces next-intl, so the real formatter is loaded explicitly.
const { createTranslator } = await vi.importActual<typeof import('next-intl')>('next-intl');

const locales = { en, zh } as const;
type LocaleName = keyof typeof locales;
const LOCALE_NAMES = Object.keys(locales) as LocaleName[];
const NAMESPACE = 'settings.browserDoctor';

const CARD_KEYS = [
  'summaryAllClear',
  'summaryNeedsAttention',
  'summaryOptional',
  'technicalDetails',
  'statusOk',
  'statusOptional',
  'statusWarning',
  'statusError',
  'statusMissing',
  'healthy',
  'unhealthy',
  'checks',
  'fix',
  'recommendations',
] as const;

const SAMPLE_VALUES = { count: 2, size: 12.4 };

function blockOf(locale: LocaleName): Record<string, unknown> {
  return locales[locale].settings.browserDoctor as Record<string, unknown>;
}

function flattenKeys(node: Record<string, unknown>, prefix = ''): string[] {
  return Object.entries(node).flatMap(([key, value]) =>
    typeof value === 'object' && value !== null
      ? flattenKeys(value as Record<string, unknown>, `${prefix}${key}.`)
      : [`${prefix}${key}`],
  );
}

function placeholdersOf(message: string): string[] {
  return [...message.matchAll(/\{\s*(\w+)\s*[,}]/g)].map((match) => match[1] ?? '').sort();
}

function translatorFor(locale: LocaleName) {
  return createTranslator({
    locale,
    messages: locales[locale],
    namespace: NAMESPACE,
    onError: (error) => {
      throw error;
    },
  });
}

describe('browser diagnostics card locale strings', () => {
  const referenceKeys = flattenKeys(blockOf('en')).sort();

  it.each(LOCALE_NAMES)('%s defines exactly the same keys as en', (locale) => {
    expect(flattenKeys(blockOf(locale)).sort()).toEqual(referenceKeys);
  });

  it.each(LOCALE_NAMES)('%s formats every hint and card key without ICU errors', (locale) => {
    const t = translatorFor(locale);
    for (const key of [...DOCTOR_HINT_KEYS, ...CARD_KEYS]) {
      const message = t(key, SAMPLE_VALUES);
      expect(message.length, `${locale}:${key}`).toBeGreaterThan(0);
      expect(message, `${locale}:${key}`).not.toMatch(/[{}#]/);
    }
  });

  it.each(LOCALE_NAMES)('%s keeps the same placeholders as en for every hint and card key', (locale) => {
    for (const key of [...DOCTOR_HINT_KEYS, ...CARD_KEYS]) {
      const reference = placeholdersOf(String((blockOf('en') as Record<string, unknown>)[key]));
      expect(placeholdersOf(String(blockOf(locale)[key])), `${locale}:${key}`).toEqual(reference);
    }
  });

  it('formats the available size with the locale number format', () => {
    expect(translatorFor('en')('memoryOk', { size: 12.4 })).toBe('12.4 GB of memory available');
    expect(translatorFor('zh')('memoryOk', { size: 12.4 })).toBe('可用内存 12.4 GB');
  });

  it('pluralizes the attention headline per locale rules', () => {
    expect(translatorFor('en')('summaryNeedsAttention', { count: 1 })).toBe('1 item needs attention');
    expect(translatorFor('en')('summaryNeedsAttention', { count: 3 })).toBe('3 items need attention');
    expect(translatorFor('zh')('summaryNeedsAttention', { count: 1 })).toBe('有 1 项需要关注');
    expect(translatorFor('zh')('summaryNeedsAttention', { count: 3 })).toBe('有 3 项需要关注');
  });
});
