/**
 * [INPUT]
 * locales/{zh,en,ja,zh-TW}.json — artifacts.inlinePreview namespace keys.
 * lib/constants/artifact.ts — LARGE_FILE_THRESHOLD constant.
 * [OUTPUT]
 * Vitest: large file inline preview i18n keys exist + LARGE_FILE_THRESHOLD is sane.
 * [POS]
 * Regression guard for large-file inline preview fallback feature.
 */

import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';
import { LARGE_FILE_THRESHOLD } from '@/lib/constants/artifact';

const LOCALES_ROOT = resolve(process.cwd(), 'locales');
const LANGUAGES = ['zh', 'en', 'ja', 'zh-TW'] as const;

const REQUIRED_KEYS = ['largeFileHint', 'viewFullscreen'] as const;

function loadArtifactsLocale(lang: string): Record<string, unknown> {
  const raw = readFileSync(resolve(LOCALES_ROOT, `${lang}.json`), 'utf-8');
  const parsed = JSON.parse(raw) as Record<string, Record<string, unknown>>;
  return (parsed['artifacts'] as Record<string, unknown>) ?? {};
}

describe('Large File Inline Preview i18n', () => {
  for (const lang of LANGUAGES) {
    describe(`locale: ${lang}`, () => {
      const artifacts = loadArtifactsLocale(lang);
      const inlinePreview = artifacts['inlinePreview'] as Record<string, string> | undefined;

      it('has inlinePreview section', () => {
        expect(inlinePreview).toBeDefined();
      });

      for (const key of REQUIRED_KEYS) {
        it(`has key: ${key}`, () => {
          const value = inlinePreview?.[key];
          expect(value).toBeDefined();
          expect(typeof value).toBe('string');
          if (typeof value !== 'string') {
            return;
          }
          expect(value.length).toBeGreaterThan(0);
        });
      }

      it('largeFileHint contains {size} placeholder', () => {
        expect(inlinePreview?.['largeFileHint']).toContain('{size}');
      });
    });
  }
});

describe('LARGE_FILE_THRESHOLD', () => {
  it('is a positive number', () => {
    expect(LARGE_FILE_THRESHOLD).toBeGreaterThan(0);
  });

  it('equals 1MB (1048576 bytes)', () => {
    expect(LARGE_FILE_THRESHOLD).toBe(1024 * 1024);
  });

  it('is not unreasonably small or large', () => {
    expect(LARGE_FILE_THRESHOLD).toBeGreaterThanOrEqual(256 * 1024);
    expect(LARGE_FILE_THRESHOLD).toBeLessThanOrEqual(10 * 1024 * 1024);
  });
});
