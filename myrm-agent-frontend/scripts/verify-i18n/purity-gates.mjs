/**
 * [INPUT] i18n-shell-core::resolvePath / isLegitSameValue (POS: 翻译壳检测共享逻辑)
 *         parity-config::EN_PURITY_ALLOWED_KEYS / SCRIPT_RESIDUE_ALLOWED_KEYS / isParityExemptKey (POS: 验证 9 配置装载与豁免键)
 *         value-rules::containsResidue / isEnglishSentenceResidue / *_RE (POS: 纯文本判据)
 *         report::reportKeys (POS: 违规打印)
 * [OUTPUT] verifyEnPurity / verifyForeignScript / verifySimplifiedGlyphs / verifyEnglishSentenceResidue
 * [POS] verify-i18n 的语言纯净门禁（9f/9g/9h/9j/9k）：en 不得混入非拉丁文字；ko/de 不得残留汉字假名；zh-TW/ja 不得残留简体独有字形；非拉丁系语言不得整条仍是英文句子。每个门禁打印违规并返回违规键供上层汇总。
 */

import { isLegitSameValue, resolvePath } from '../i18n-shell-core.mjs';
import { EN_PURITY_ALLOWED_KEYS, SCRIPT_RESIDUE_ALLOWED_KEYS, isParityExemptKey } from './parity-config.mjs';
import { reportKeys } from './report.mjs';
import {
  FOREIGN_SCRIPT_DE_RE,
  FOREIGN_SCRIPT_RE,
  NON_LATIN_RE,
  containsResidue,
  isEnglishSentenceResidue,
} from './value-rules.mjs';

/** 在 en 叶子键中收集 `lang` 的值含 `residueRe` 的键（动态示例键与 `isAllowed` 命中的键除外）。 */
function collectResidueKeys(ctx, lang, enLeaves, residueRe, isAllowed) {
  const localeData = ctx.translations[lang];
  const errors = [];
  for (const key of enLeaves) {
    if (isParityExemptKey(key) || isAllowed(key)) {
      continue;
    }
    if (containsResidue(resolvePath(localeData, key), residueRe)) {
      errors.push(key);
    }
  }
  return errors;
}

// 9f. en.json 纯净性（SSOT 语言纯净门禁）：en 叶子值不得混入非拉丁文字（语言名/品牌 allowlist 豁免）
export function verifyEnPurity(ctx, config, enLeaves) {
  const { allowedSameKeys } = config.shellAllowlists;
  const isAllowed = (key) =>
    EN_PURITY_ALLOWED_KEYS.has(key) || allowedSameKeys.has(key) || config.allowedMixedKeys.has(key);
  const errors = collectResidueKeys(ctx, 'en', enLeaves, NON_LATIN_RE, isAllowed);
  if (errors.length > 0) {
    reportKeys(`  ❌ en.json 存在 ${errors.length} 个混入非拉丁文字的键（SSOT 污染，须修复为纯英文）：`, errors);
    ctx.hasErrors = true;
  }
}

// 9g. 拉丁/谚文系语言（ko/de）非本语言文字纯净门禁：文案中出现汉字或日文假名即残留
//（豁免见 SCRIPT_RESIDUE_ALLOWED_KEYS）；de 额外拦截谚文（FOREIGN_SCRIPT_DE_RE）。
// 与 en 9f SSOT 纯净门禁对称。
export function verifyForeignScript(ctx, lang, enLeaves) {
  if (lang !== 'ko' && lang !== 'de') {
    return [];
  }
  const foreignScriptRe = lang === 'de' ? FOREIGN_SCRIPT_DE_RE : FOREIGN_SCRIPT_RE;
  const errors = collectResidueKeys(ctx, lang, enLeaves, foreignScriptRe, (key) =>
    SCRIPT_RESIDUE_ALLOWED_KEYS.has(key),
  );
  if (errors.length > 0) {
    reportKeys(`  ❌ ${lang}.json 存在 ${errors.length} 个含非本语言文字的键：`, errors);
    ctx.hasErrors = true;
  }
  return errors;
}

// 9h/9j. 简体独有字形纯净门禁：zh-TW 相对繁体字形、ja 相对日文新字体字形，出现即残留
//（豁免见 SCRIPT_RESIDUE_ALLOWED_KEYS）。与 en 9f / ko-de 9g 纯净门禁对称。
export function verifySimplifiedGlyphs(ctx, lang, enLeaves, simplifiedGlyphGates) {
  const allErrors = [];
  for (const gate of simplifiedGlyphGates) {
    if (lang !== gate.lang || !gate.re) {
      continue;
    }
    const gateErrors = collectResidueKeys(ctx, lang, enLeaves, gate.re, (key) => SCRIPT_RESIDUE_ALLOWED_KEYS.has(key));
    if (gateErrors.length > 0) {
      reportKeys(`  ❌ ${lang}.json 存在 ${gateErrors.length} 个含${gate.label}的键：`, gateErrors);
      ctx.hasErrors = true;
    }
    allErrors.push(...gateErrors);
  }
  return allErrors;
}

// 9k. 非拉丁系语言（zh/ja/ko/zh-TW）句子级纯英文残留门禁：
// 整条文案仍是英文句子（值≠en 且纯 ASCII 且含英文实义句子）即残留。
// 与 9g/9h/9j 的「混入字形」检测互补（后者拦混入、本检测拦整条）；
// 字段名/品牌名/单技术词天然豁免。de 为拉丁语系，纯英文残留无法以字符级
// 与合法德文区分，不适用（由 9g 汉字/假名拦截 + glossary 语义词兜底）。
// 数组叶子逐元素判定（与 9d checkArray / 9g-9j containsResidue 对称）。
export function verifyEnglishSentenceResidue(ctx, config, lang, enLeaves) {
  if (lang !== 'zh' && lang !== 'ja' && lang !== 'ko' && lang !== 'zh-TW') {
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
    if (localeLeaf === '' || /[\u0080-\uFFFF]/.test(localeLeaf)) {
      return; // 空串/已含本语言字符
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
    if (isParityExemptKey(key) || shellAllowlists.allowedSameKeys.has(key)) {
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
