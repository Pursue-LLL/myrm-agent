/**
 * [INPUT] i18n-shell-core::resolvePath / hasNonAsciiLetter / isLegitSameValue (POS: 翻译壳检测共享逻辑)
 *         parity-config::EN_PURITY_ALLOWED_KEYS (POS: 验证 9 配置装载与豁免键)
 *         value-rules::containsResidue / isEnglishSentenceResidue / NON_LATIN_RE (POS: 纯文本判据)
 *         report::reportKeys (POS: 违规打印)
 * [OUTPUT] verifyEnPurity / verifyEnglishSentenceResidue
 * [POS] verify-i18n 的语言纯净门禁（9f/9k）：en 不得混入非拉丁文字；zh 不得整条仍是英文句子。每个门禁打印违规并返回违规键供上层汇总。
 */

import { hasNonAsciiLetter, isLegitSameValue, resolvePath } from '../i18n-shell-core.mjs';
import { EN_PURITY_ALLOWED_KEYS } from './parity-config.mjs';
import { reportKeys } from './report.mjs';
import { NON_LATIN_RE, containsResidue, isEnglishSentenceResidue } from './value-rules.mjs';

// 9f. en.json 纯净性（SSOT 语言纯净门禁）：en 叶子值不得混入非拉丁文字（语言名/品牌 allowlist 豁免）
export function verifyEnPurity(ctx, config, enLeaves) {
  const { allowedSameKeys } = config.shellAllowlists;
  const isAllowed = (key) =>
    EN_PURITY_ALLOWED_KEYS.has(key) || allowedSameKeys.has(key) || config.allowedMixedKeys.has(key);
  const localeData = ctx.translations.en;
  const errors = enLeaves.filter(
    (key) => !isAllowed(key) && containsResidue(resolvePath(localeData, key), NON_LATIN_RE),
  );
  if (errors.length > 0) {
    reportKeys(`  ❌ en.json 存在 ${errors.length} 个混入非拉丁文字的键（SSOT 污染，须修复为纯英文）：`, errors);
    ctx.hasErrors = true;
  }
}

// 9k. 非拉丁系语言（zh）句子级纯英文残留门禁：
// 整条文案仍是英文句子（值≠en 且不含非 ASCII 字母且含英文实义句子）即残留。
// 字段名/品牌名/单技术词天然豁免。
// 数组叶子逐元素判定（与 9d checkArray / 9f containsResidue 对称）。
export function verifyEnglishSentenceResidue(ctx, config, lang, enLeaves) {
  if (lang !== 'zh') {
    return [];
  }
  const { shellAllowlists } = config;
  const localeData = ctx.translations[lang];
  const errors = [];

  const checkLeaf = (key, enLeaf, localeLeaf) => {
    if (typeof enLeaf !== 'string' || typeof localeLeaf !== 'string') {
      return;
    }
    if (localeLeaf === enLeaf) {
      return; // 与 en 同值走壳检测（collectTranslationShells）
    }
    if (localeLeaf === '' || hasNonAsciiLetter(localeLeaf)) {
      return; // 空串/已含本语言文字（非 ASCII 标点不算）
    }
    if (isLegitSameValue(localeLeaf)) {
      return; // 技术格式/占位模板/URL 等合法保留
    }
    if (shellAllowlists.allowedSameValues.has(localeLeaf)) {
      return;
    }
    if (isEnglishSentenceResidue(localeLeaf)) {
      errors.push(key);
    }
  };

  for (const key of enLeaves) {
    if (shellAllowlists.allowedSameKeys.has(key)) {
      continue;
    }
    const enValue = resolvePath(ctx.translations.en, key);
    const localeValue = resolvePath(localeData, key);
    if (Array.isArray(enValue)) {
      if (!Array.isArray(localeValue)) {
        continue;
      }
      enValue.forEach((item, index) => {
        checkLeaf(`${key}[${index}]`, item, localeValue[index]);
      });
    } else {
      checkLeaf(key, enValue, localeValue);
    }
  }
  if (errors.length > 0) {
    reportKeys(`  ❌ ${lang}.json 存在 ${errors.length} 个句子级纯英文残留键：`, errors);
    ctx.hasErrors = true;
  }
  return errors;
}
