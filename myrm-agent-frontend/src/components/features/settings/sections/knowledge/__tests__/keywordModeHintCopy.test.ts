/**
 * Keyword-mode hint copy contract (all six locales).
 *
 * Configuring an embedding model enables semantic retrieval for new writes; memories already
 * stored in the BM25 sparse mirror stay keyword-retrievable and are not backfilled into dense
 * collections. The hint must therefore never promise an automatic upgrade of existing memories —
 * that wording was shipped once and had to be corrected. It must also point at the setting with
 * the vocabulary the rest of the UI uses for that model.
 */
import { describe, expect, it } from 'vitest';
import de from '@/../locales/de.json';
import en from '@/../locales/en.json';
import ja from '@/../locales/ja.json';
import ko from '@/../locales/ko.json';
import zh from '@/../locales/zh.json';
import zhTW from '@/../locales/zh-TW.json';

const locales: Record<string, { hint: string; modelTerm: RegExp }> = {
  de: { hint: de.memory.keywordModeHint, modelTerm: /Embedding-Modell/ },
  en: { hint: en.memory.keywordModeHint, modelTerm: /embedding model/i },
  ja: { hint: ja.memory.keywordModeHint, modelTerm: /エンベディングモデル/ },
  ko: { hint: ko.memory.keywordModeHint, modelTerm: /임베딩 모델/ },
  zh: { hint: zh.memory.keywordModeHint, modelTerm: /嵌入模型/ },
  'zh-TW': { hint: zhTW.memory.keywordModeHint, modelTerm: /嵌入模型/ },
};

const OVER_PROMISE = /自动升级|自動升級|upgrade|aufgerüstet|アップグレード|업그레이드/i;

describe('memory.keywordModeHint', () => {
  it.each(Object.entries(locales))('%s names the keyword mode and the embedding model', (_locale, { hint, modelTerm }) => {
    expect(hint.length).toBeGreaterThan(0);
    expect(hint).toMatch(modelTerm);
  });

  it.each(Object.entries(locales))('%s does not promise an automatic semantic upgrade', (_locale, { hint }) => {
    expect(hint).not.toMatch(OVER_PROMISE);
  });
});
