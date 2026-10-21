/**
 * [INPUT]
 * locales/{zh,en,ja,ko,de}.json — artifacts namespace strings for ArtifactsCenter.
 * [OUTPUT]
 * Vitest: every ArtifactsCenter `useTranslations('artifacts')` key exists in all locales.
 * [POS]
 * Regression guard for raw i18n keys (e.g. artifacts.empty) on /artifacts page.
 */

import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';

const LOCALES_ROOT = resolve(process.cwd(), 'locales');
const LANGUAGES = ['zh', 'en', 'ja', 'ko', 'de'] as const;

const ARTIFACTS_CENTER_KEYS = [
  'title',
  'empty',
  'select_prompt',
  'no_desc',
  'version_history',
  'tamper_free',
  'corrupted',
  'verifying',
  'verify_hash',
  'loading_versions',
  'auto_saved_version',
  'preview',
  'download',
] as const;

function loadLocale(lang: (typeof LANGUAGES)[number]): Record<string, unknown> {
  const raw = readFileSync(resolve(LOCALES_ROOT, `${lang}.json`), 'utf-8');
  return JSON.parse(raw) as Record<string, unknown>;
}

describe('ArtifactsCenter locale keys', () => {
  for (const lang of LANGUAGES) {
    it(`${lang}.json defines all ArtifactsCenter artifacts keys`, () => {
      const data = loadLocale(lang);
      const artifacts = data.artifacts as Record<string, unknown> | undefined;
      expect(artifacts).toBeDefined();

      for (const key of ARTIFACTS_CENTER_KEYS) {
        const value = artifacts?.[key];
        expect(typeof value, `${lang}.artifacts.${key}`).toBe('string');
        expect((value as string).length, `${lang}.artifacts.${key}`).toBeGreaterThan(0);
      }
    });
  }
});
