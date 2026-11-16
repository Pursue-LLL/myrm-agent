/**
 * Keyword-mode hint copy contract (both locales).
 *
 * Configuring an embedding model enables semantic retrieval for new writes; memories already
 * stored in the BM25 sparse mirror stay keyword-retrievable and are not backfilled into dense
 * collections. The hint must therefore never promise an automatic upgrade of existing memories —
 * that wording was shipped once and had to be corrected. It must also point at the setting with
 * the vocabulary the rest of the UI uses for that model.
 */
import { describe, expect, it } from 'vitest';
import en from '@/../locales/en.json';
import zh from '@/../locales/zh.json';

const locales: Record<string, { hint: string; modelTerm: RegExp }> = {
  en: { hint: en.memory.keywordModeHint, modelTerm: /embedding model/i },
  zh: { hint: zh.memory.keywordModeHint, modelTerm: /嵌入模型/ },
};

const OVER_PROMISE = /自动升级|upgrade/i;

describe('memory.keywordModeHint', () => {
  it.each(Object.entries(locales))('%s names the keyword mode and the embedding model', (_locale, { hint, modelTerm }) => {
    expect(hint.length).toBeGreaterThan(0);
    expect(hint).toMatch(modelTerm);
  });

  it.each(Object.entries(locales))('%s does not promise an automatic semantic upgrade', (_locale, { hint }) => {
    expect(hint).not.toMatch(OVER_PROMISE);
  });
});
