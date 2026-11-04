import { describe, expect, it, vi } from 'vitest';

import en from '../../../../locales/en.json';
import zh from '../../../../locales/zh.json';
import { type KeyedTranslator, translateOrRaw } from '../translateOrRaw';

// The global test setup replaces next-intl; the real translator over the shipped messages is what shows how a missing
// key behaves.
const { createTranslator } = await vi.importActual<typeof import('next-intl')>('next-intl');

const bundles = { en, zh } as const;

// Components see `useTranslations(namespace)` with plain string keys; `createTranslator` derives key types from the
// message object, so it is viewed through the contract the helper declares.
const errorCategoryTranslator = (locale: keyof typeof bundles): KeyedTranslator =>
  createTranslator({
    locale,
    messages: bundles[locale],
    namespace: 'progressSteps.errorCategories',
  }) as unknown as KeyedTranslator;

describe('translateOrRaw', () => {
  it('translates a key the language pack holds', () => {
    expect(translateOrRaw(errorCategoryTranslator('en'), 'oom_killed', 'oom_killed')).toBe('OOM Killed');
    expect(translateOrRaw(errorCategoryTranslator('zh'), 'oom_killed', 'oom_killed')).toBe('OOM 强杀');
  });

  it('returns the raw value for a key the language pack lacks, never the key path', () => {
    expect(translateOrRaw(errorCategoryTranslator('en'), 'brand_new_category', 'brand_new_category')).toBe(
      'brand_new_category',
    );
  });
});
