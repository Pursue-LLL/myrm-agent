/**
 * [INPUT] i18n-shell-core::collectTranslationShells / resolvePath / walkTypes (POS: 翻译壳检测共享逻辑)
 *         context::LANGUAGES (POS: 共享上下文与支持语言)
 *         parity-config::loadParityConfig / loadGlyphSet / isParityExemptKey (POS: 验证 9 配置装载与豁免键)
 *         purity-gates::verify* (POS: 语言纯净门禁 9f-9k)
 *         value-rules::isBilingualDirty / placeholderSet (POS: 纯文本判据)
 *         report::reportKeys / reportShells (POS: 违规打印)
 * [OUTPUT] verifyLocaleParity
 * [POS] verify-i18n 全量对齐门禁（验证 9）：每个非 en 语言对 en 做 key parity（9a 缺键 / 9b 孤儿键）、叶子类型一致（9c）、
 *       占位符一致 + glossary forbidden + 双语对照 + 异常哨兵（9d）、翻译壳，再串联 purity-gates 的语言纯净门禁（9f-9k）。
 *       ICU 语法由 `check-icu-syntax.mjs` 负责，此处不重复校验。
 */

import { collectTranslationShells, resolvePath, walkTypes } from '../i18n-shell-core.mjs';
import { LANGUAGES } from './context.mjs';
import { isParityExemptKey, loadGlyphSet, loadParityConfig } from './parity-config.mjs';
import {
  verifyEnPurity,
  verifyEnglishSentenceResidue,
  verifyForeignScript,
  verifySimplifiedGlyphs,
} from './purity-gates.mjs';
import { reportKeys, reportShells } from './report.mjs';
import { isBilingualDirty, placeholderSet } from './value-rules.mjs';

/** 按 en 叶子逐值比对：占位符、glossary forbidden、双语对照、哨兵（数组叶子逐元素）。 */
function collectValueErrors(config, lang, localeData, enData, enLeaves) {
  const errors = { placeholder: [], glossary: [], bilingual: [], sentinel: [] };
  const forbiddenPatterns = config.glossaryForbiddenByLocale[lang] || [];

  const checkValue = (key, enValue, localeValue) => {
    if (typeof enValue !== 'string') {
      return;
    }
    if (typeof localeValue !== 'string') {
      return;
    }
    if (localeValue.includes('[object Object]')) {
      errors.sentinel.push(`${key} = "[object Object]"`);
      return;
    }
    if (!localeValue.trim()) {
      errors.sentinel.push(`${key} = 空字符串`);
      return;
    }
    if (placeholderSet(enValue) !== placeholderSet(localeValue)) {
      errors.placeholder.push(
        `${key}: en[${placeholderSet(enValue) || '(none)'}] vs ${lang}[${placeholderSet(localeValue) || '(none)'}]`,
      );
      return;
    }
    if (forbiddenPatterns.length > 0) {
      const lower = localeValue.toLowerCase();
      for (const pattern of forbiddenPatterns) {
        // 预编译模式：/正则/ → RegExp 实例（加载时已编译，非法正则在彼时 fail-fast 置 null）；
        // 普通模式 → 小写字符串（lower.includes 匹配）
        if (pattern === null) {
          continue;
        } // 非法正则已在加载阶段报错，此处跳过避免 null 参与匹配
        if (pattern instanceof RegExp) {
          if (pattern.test(localeValue)) {
            errors.glossary.push(`${key} = forbidden pattern /${pattern.source}/`);
            break;
          }
        } else if (lower.includes(pattern)) {
          errors.glossary.push(`${key} = forbidden pattern ${JSON.stringify(pattern)}`);
          break;
        }
      }
    }
    if (isBilingualDirty(localeValue) && !enValue.includes(' / ')) {
      if (!config.allowedMixedValues.has(localeValue) && !config.allowedMixedKeys.has(key)) {
        errors.bilingual.push(`${key} = ${JSON.stringify(localeValue.slice(0, 80))}`);
      }
    }
  };

  const checkArray = (key, enArr, localeArr) => {
    enArr.forEach((item, index) => {
      const localeItem = Array.isArray(localeArr) ? localeArr[index] : undefined;
      if (typeof item === 'string' && typeof localeItem === 'string') {
        checkValue(`${key}[${index}]`, item, localeItem);
      }
    });
  };

  for (const key of enLeaves) {
    if (isParityExemptKey(key)) {
      continue;
    }
    const enValue = resolvePath(enData, key);
    const localeValue = resolvePath(localeData, key);
    if (enValue === undefined || localeValue === undefined) {
      continue;
    }
    if (Array.isArray(enValue)) {
      checkArray(key, enValue, localeValue);
    } else {
      checkValue(key, enValue, localeValue);
    }
  }
  return errors;
}

function verifyOneLocale(ctx, config, lang, enTypes, enLeaves, simplifiedGlyphGates) {
  const enData = ctx.translations.en;
  const data = ctx.translations[lang];
  const localeTypes = new Map();
  walkTypes(data, '', localeTypes);

  // 9a. key parity (en vs zh baseline SSOT)
  const missing = enLeaves.filter((key) => !localeTypes.has(key) && !isParityExemptKey(key));
  if (missing.length > 0) {
    console.error(`  ❌ ${lang}.json 缺少 ${missing.length} 个 en 键：`);
    missing.slice(0, 15).forEach((key) => console.error(`     - ${key}`));
    if (missing.length > 15) {
      console.error(`     ... 还有 ${missing.length - 15} 个`);
    }
    ctx.hasErrors = true;
  }

  // 9b. 孤儿键（en 中不存在的键）→ ERROR，须清理；无豁免（en 是 SSOT，任何语言都不得独有键）
  const orphanKeys = [...localeTypes.keys()].filter((key) => !enTypes.has(key));
  if (orphanKeys.length > 0) {
    reportKeys(`  ❌ ${lang}.json 存在 ${orphanKeys.length} 个 en 中没有的键（孤儿键，须清理）：`, orphanKeys);
    ctx.hasErrors = true;
  }

  // 9c. 类型一致
  const typeMismatches = [];
  for (const [key, enType] of enTypes) {
    if (isParityExemptKey(key)) {
      continue;
    }
    if (!localeTypes.has(key)) {
      continue;
    }
    const localeType = localeTypes.get(key);
    if (localeType !== enType) {
      typeMismatches.push(`${key} (en:${enType} vs ${lang}:${localeType})`);
    }
  }
  if (typeMismatches.length > 0) {
    reportKeys(`  ❌ ${lang}.json 存在 ${typeMismatches.length} 个类型不一致键：`, typeMismatches);
    ctx.hasErrors = true;
  }

  // 9d. 占位符一致 + glossary forbidden + 双语对照 + 哨兵（壳检测见 collectTranslationShells）
  const valueErrors = collectValueErrors(config, lang, data, enData, enLeaves);
  const shellErrors = collectTranslationShells(enData, data, config.shellAllowlists)
    .filter(({ key }) => !isParityExemptKey(key))
    .map(({ key, en }) => ({ path: key, value: en }));
  reportShells(ctx, lang, shellErrors);
  const valueReports = [
    [valueErrors.glossary, '个 glossary forbidden 违规'],
    [valueErrors.placeholder, '个占位符不匹配'],
    [valueErrors.bilingual, '个双语对照脏值（本地语 / English 并存）'],
    [valueErrors.sentinel, '个异常哨兵'],
  ];
  for (const [errors, noun] of valueReports) {
    if (errors.length === 0) {
      continue;
    }
    reportKeys(`  ❌ ${lang}.json 存在 ${errors.length} ${noun}：`, errors);
    ctx.hasErrors = true;
  }

  const foreignScriptErrors = verifyForeignScript(ctx, lang, enLeaves);
  const simplifiedGlyphErrors = verifySimplifiedGlyphs(ctx, lang, enLeaves, simplifiedGlyphGates);
  const pureEnErrors = verifyEnglishSentenceResidue(ctx, config, lang, enLeaves);

  const failureGroups = [
    missing,
    orphanKeys,
    typeMismatches,
    shellErrors,
    valueErrors.placeholder,
    valueErrors.glossary,
    valueErrors.bilingual,
    valueErrors.sentinel,
    foreignScriptErrors,
    simplifiedGlyphErrors,
    pureEnErrors,
  ];
  if (failureGroups.every((errors) => errors.length === 0)) {
    console.log(`  ✅ ${lang}.json 全量 parity / 占位符 / 壳 / glossary / 双语对照 / 纯净门禁 检测 通过`);
  }
}

// 验证9: 全量 key parity + 类型一致 + 占位符 + 壳检测 + 哨兵（所有语言 vs en）
export function verifyLocaleParity(ctx) {
  console.log('\n📋 验证全量 key parity / 类型 / 占位符 / 翻译壳 / 异常哨兵...');

  const config = loadParityConfig(ctx);
  const enTypes = new Map();
  walkTypes(ctx.translations.en, '', enTypes);
  const enLeaves = [...enTypes.keys()];

  // zh-TW 相对繁体字形、ja 相对日文新字体字形；集合由 generate-simplified-glyphs.mjs 从 zh.json 语料 + opencc 生成
  const simplifiedGlyphGates = [
    {
      lang: 'zh-TW',
      re: loadGlyphSet(ctx, 'scripts/zh-simplified-glyphs.txt', '简体字形集合'),
      label: '简体独有字形（须转繁体）',
    },
    {
      lang: 'ja',
      re: loadGlyphSet(ctx, 'scripts/ja-simplified-glyphs.txt', 'ja 简体字形集合'),
      label: '简体独有字形（须转日文标准字形）',
    },
  ];

  verifyEnPurity(ctx, config, enLeaves);

  for (const lang of LANGUAGES) {
    if (!ctx.translations[lang] || lang === 'en') {
      continue;
    }
    verifyOneLocale(ctx, config, lang, enTypes, enLeaves, simplifiedGlyphGates);
  }
}
