/**
 * [INPUT]
 * locales/{zh,en,zh-TW,ja,de,ko}.json — trunk workflow strings.
 * [OUTPUT]
 * Vitest: trunk badge, admit reason, and pin-hint keys exist in all locales.
 * [POS]
 * Regression guard for raw i18n keys added by the trunk workflow feature.
 */

import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';

const LOCALES_ROOT = resolve(process.cwd(), 'locales');
const LANGUAGES = ['zh', 'en', 'zh-TW', 'ja', 'de', 'ko'] as const;

const LIBRARY_KEYS = [
  'trunkBadge',
  'admitEvidenceMissing',
  'admitArgsInvalid',
  'admitTemplateGone',
  'admitTrustPolicy',
  'admitCriteriaOpen',
  'admitDeniedGeneric',
] as const;

function loadLocale(lang: (typeof LANGUAGES)[number]): Record<string, unknown> {
  const raw = readFileSync(resolve(LOCALES_ROOT, `${lang}.json`), 'utf-8');
  return JSON.parse(raw) as Record<string, unknown>;
}

function section(locale: Record<string, unknown>, path: string[]): Record<string, unknown> {
  let node: unknown = locale;
  for (const key of path) {
    node = (node as Record<string, unknown>)[key];
  }
  return node as Record<string, unknown>;
}

describe('Trunk workflow locale keys', () => {
  for (const lang of LANGUAGES) {
    it(`${lang}.json defines all trunk workflowTemplates keys`, () => {
      const locale = loadLocale(lang);
      const templates = section(locale, ['settings', 'skills', 'workflowTemplates']);
      for (const key of LIBRARY_KEYS) {
        expect(typeof templates[key], `${lang} missing ${key}`).toBe('string');
      }
    });

    it(`${lang}.json defines the trunk pin hint`, () => {
      const locale = loadLocale(lang);
      const suggestion = section(locale, ['chat', 'workflowSuggestion']);
      expect(typeof suggestion.trunkPinHint, `${lang} missing trunkPinHint`).toBe('string');
    });
  }
});
