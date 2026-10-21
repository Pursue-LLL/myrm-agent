/**
 * [INPUT] locales/{lang}.json (POS: 六语系 SSOT 文案)
 * [OUTPUT] LANGUAGES / createContext / loadTranslations
 * [POS] 共享上下文与支持语言：支持语言清单、已加载的 locale 数据与全局失败标志（各检查模块只写 `ctx.hasErrors`，由入口统一决定退出码）。
 */

import { readFileSync } from 'fs';
import { resolve } from 'path';

// 支持的语言（必须与 src/i18n/config.ts locales 一致）
export const LANGUAGES = ['zh', 'en', 'ja', 'ko', 'de', 'zh-TW'];

export function createContext(rootDir) {
  return { rootDir, translations: {}, hasErrors: false };
}

/** 读取全部语言文件到 `ctx.translations`；无法解析的语言置 hasErrors 且保持缺席。 */
export function loadTranslations(ctx) {
  for (const lang of LANGUAGES) {
    const filePath = resolve(ctx.rootDir, `locales/${lang}.json`);
    try {
      ctx.translations[lang] = JSON.parse(readFileSync(filePath, 'utf-8'));
      console.log(`✅ 已加载 ${lang}.json`);
    } catch (error) {
      console.error(`❌ 无法加载 ${lang}.json: ${error.message}`);
      ctx.hasErrors = true;
    }
  }
}
