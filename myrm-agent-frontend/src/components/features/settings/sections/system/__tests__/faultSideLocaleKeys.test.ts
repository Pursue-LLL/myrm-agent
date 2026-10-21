/**
 * [INPUT]
 * locales/{zh,en,zh-TW,ja,ko,de}.json — fault-side attribution strings.
 * [OUTPUT]
 * Vitest: InteractionCentricFailureLocalizerStack i18n keys exist and are
 * non-empty in every supported locale.
 * [POS]
 * Regression guard for fault-side attribution UI keys surfaced in ProgressSteps
 * (`faultSides.*`), the compaction dropped-manifest card, and the execution
 * trace timeline.
 */

import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';

const LOCALES_ROOT = resolve(process.cwd(), 'locales');
const LANGUAGES = ['zh', 'en', 'zh-TW', 'ja', 'ko', 'de'] as const;

const FAULT_SIDE_KEYS = ['model', 'harness_tool', 'harness_pipeline', 'env', 'grader', 'owner'] as const;

function loadLocale(lang: (typeof LANGUAGES)[number]): Record<string, unknown> {
  const raw = readFileSync(resolve(LOCALES_ROOT, `${lang}.json`), 'utf-8');
  return JSON.parse(raw) as Record<string, unknown>;
}

describe('fault-side attribution locale keys', () => {
  for (const lang of LANGUAGES) {
    it(`${lang}.json defines all faultSides keys`, () => {
      const data = loadLocale(lang);
      const progressSteps = data.progressSteps as Record<string, unknown> | undefined;
      expect(progressSteps).toBeDefined();

      const faultSides = progressSteps?.faultSides as Record<string, unknown> | undefined;
      expect(faultSides, `${lang}.progressSteps.faultSides`).toBeDefined();

      for (const key of FAULT_SIDE_KEYS) {
        const value = faultSides?.[key];
        expect(typeof value, `${lang}.progressSteps.faultSides.${key}`).toBe('string');
        expect((value as string).length, `${lang}.progressSteps.faultSides.${key}`).toBeGreaterThan(0);
      }
    });

    it(`${lang}.json defines the dropped-manifest keys`, () => {
      const data = loadLocale(lang);
      const progressSteps = data.progressSteps as Record<string, unknown> | undefined;
      for (const key of ['dropped_manifest_title', 'dropped_manifest_more'] as const) {
        const value = progressSteps?.[key];
        expect(typeof value, `${lang}.progressSteps.${key}`).toBe('string');
        expect((value as string).length, `${lang}.progressSteps.${key}`).toBeGreaterThan(0);
      }
    });

    it(`${lang}.json defines the trace first-irrecoverable keys`, () => {
      const data = loadLocale(lang);
      const settings = data.settings as Record<string, unknown> | undefined;
      const sessionAnalytics = settings?.sessionAnalytics as Record<string, unknown> | undefined;
      const trace = sessionAnalytics?.trace as Record<string, unknown> | undefined;
      expect(trace, `${lang}.settings.sessionAnalytics.trace`).toBeDefined();
      for (const key of ['firstIrrecoverable', 'recoverySteps'] as const) {
        const value = trace?.[key];
        expect(typeof value, `${lang}.settings.sessionAnalytics.trace.${key}`).toBe('string');
        expect((value as string).length, `${lang}.settings.sessionAnalytics.trace.${key}`).toBeGreaterThan(0);
      }
    });
  }
});
