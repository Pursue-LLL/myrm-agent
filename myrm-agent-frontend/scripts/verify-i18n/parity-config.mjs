/**
 * [INPUT] i18n-shell-core::loadShellAllowlist (POS: 翻译壳检测共享逻辑)
 *         scripts/i18n-shell-allowlist.json (POS: 壳/双语豁免) + scripts/i18n-glossary.json (POS: 术语禁用表) + scripts/{zh,ja}-simplified-glyphs.txt (POS: 简体独有字形集合)
 * [OUTPUT] loadParityConfig / loadGlyphSet / EN_PURITY_ALLOWED_KEYS / SCRIPT_RESIDUE_ALLOWED_KEYS
 * [POS] verify-i18n 全量门禁（验证 9）的配置装载与豁免键：豁免清单、预编译 glossary 与字形集合；任何装载失败都置 hasErrors（fail-safe），不静默放行。
 */

import { readFileSync } from 'fs';
import { resolve } from 'path';
import { loadShellAllowlist } from '../i18n-shell-core.mjs';

/** en（SSOT）纯净性豁免键：语言名本身即目标语言文字。 */
export const EN_PURITY_ALLOWED_KEYS = new Set([
  'settings.languageOptions.chinese',
  'settings.languageOptions.chineseTraditional',
  'settings.languageOptions.japanese',
  'settings.languageOptions.korean',
  'settings.languageOptions.german',
]);

/**
 * 跨语言术语豁免：agent.formalKoreanReplies.title/description 描述韩语敬语体 .합니다
 * （de 中写成「합니다体」/「합니다체」，「体」为日语汉字、「체」为谚文，有意保留，非残留）。
 */
const KOREAN_FORMAL_TERM_KEYS = ['agent.formalKoreanReplies.title', 'agent.formalKoreanReplies.description'];

/** 非本语言文字残留门禁（ko/de 汉字假名 9g、zh-TW/ja 简体字形 9h/9j）共用的豁免键：en 语言名 + 跨语言术语。 */
export const SCRIPT_RESIDUE_ALLOWED_KEYS = new Set([...EN_PURITY_ALLOWED_KEYS, ...KOREAN_FORMAL_TERM_KEYS]);

/**
 * 装载壳检测 allowlist 与 glossary。
 * 按步骤逐项赋值：中途失败时已装载的部分保留、其余保持空集合（与失败位置一致的降级口径）。
 *
 * @returns {{
 *   shellAllowlists: { allowedSameValues: Set<string>, allowedSameKeys: Set<string> },
 *   allowedMixedValues: Set<string>,
 *   allowedMixedKeys: Set<string>,
 *   glossaryForbiddenByLocale: Record<string, Array<string | RegExp | null>>,
 * }}
 */
export function loadParityConfig(ctx) {
  const { rootDir } = ctx;
  const config = {
    shellAllowlists: { allowedSameValues: new Set(), allowedSameKeys: new Set() },
    allowedMixedValues: new Set(),
    allowedMixedKeys: new Set(),
    glossaryForbiddenByLocale: {},
  };
  try {
    config.shellAllowlists = loadShellAllowlist(rootDir);
    const allowlist = JSON.parse(readFileSync(resolve(rootDir, 'scripts/i18n-shell-allowlist.json'), 'utf-8'));
    config.allowedMixedValues = new Set(allowlist.allowedMixedValues || []);
    config.allowedMixedKeys = new Set(allowlist.allowedMixedKeys || []);
    const glossary = JSON.parse(readFileSync(resolve(rootDir, 'scripts/i18n-glossary.json'), 'utf-8'));
    for (const [locale, localeConfig] of Object.entries(glossary.locales || {})) {
      // 预编译：字符串模式转小写供 lower.includes 匹配；/正则/ 模式编译为 RegExp 复用
      //（避免逐 key 比对时重复 new RegExp；非法正则在此 fail-fast）
      config.glossaryForbiddenByLocale[locale] = (localeConfig.forbidden || []).map((pattern) => {
        const text = String(pattern);
        if (text.startsWith('/') && text.endsWith('/') && text.length > 2) {
          try {
            return new RegExp(text.slice(1, -1), 'i');
          } catch (error) {
            const message = error instanceof Error ? error.message : String(error);
            console.error(`  ❌ ${locale}.json glossary 非法正则 ${JSON.stringify(text)}: ${message}`);
            ctx.hasErrors = true;
            return null;
          }
        }
        return text.toLowerCase();
      });
    }
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    console.error(`  ❌ 无法加载 i18n allowlist/glossary: ${message}`);
    ctx.hasErrors = true;
  }
  return config;
}

/**
 * 加载简体独有字形集合文件并编译为检测正则。
 * 集合来源：scripts/zh-simplified-glyphs.txt（zh-TW，opencc cn→tw 从 zh 语料生成）、
 * scripts/ja-simplified-glyphs.txt（ja，opencc cn→jp 生成）。
 * 文件缺失/损坏时置 hasErrors 并返回 null（门禁 fail-safe）。
 */
export function loadGlyphSet(ctx, relativePath, label) {
  try {
    const glyphs = readFileSync(resolve(ctx.rootDir, relativePath), 'utf-8').trim();
    return new RegExp(`[${glyphs}]`);
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    console.error(`  ❌ 无法加载 ${relativePath}（${label}）: ${message}`);
    ctx.hasErrors = true;
    return null;
  }
}
