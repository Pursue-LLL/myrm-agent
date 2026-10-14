#!/usr/bin/env node
/**
 * 翻译完整性验证脚本（i18n 质量门禁）。
 *
 * - metadata.settingsTabs / settings.menu / settings.developer 完整性
 * - agent.configPanel / kanban / artifacts / cron 关键 string 键在全部 6 种语言均存在（防 MISSING_MESSAGE）
 * - SSR shell 组件不得 useTranslations(deferred namespace)（与 locale-manifest.ts 对齐）
 * - home-route settings i18n shell contract（scan-home-i18n-shell.mjs）
 * - 全语言 vs en：key parity（缺键=ERROR / 孤儿键=ERROR）、叶子类型一致、ICU 占位符变量一致、
 *   翻译壳检测（含单 token 英文壳，豁免见 scripts/i18n-shell-allowlist.json）、
 *   双语对照脏值检测（"本地语 / English" 并存）、异常哨兵（[object Object] / 空串）
 * - en 纯净性门禁：en（SSOT）叶子值不得混入 CJK（语言名 allowlist 豁免），防 SSOT 污染连锁
 * - ko/de 非本语言文字纯净门禁：拉丁/谚文系语言（ko/de）文案中出现汉字或日文假名即残留
 *   （语言名/跨语言术语豁免），与 en 9f 对称
 * - zh-TW/ja 简体独有字形纯净门禁：繁体中文/日文文案中出现简体独有字形（相对繁体/日文新字体）
 *   即残留（语言名/跨语言术语豁免），与 en 9f / ko-de 9g 对称
 * - zh/ja/ko/zh-TW 句子级纯英文残留门禁：非拉丁系语言整条文案仍是英文句子即残留
 *   （值≠en 且纯 ASCII 且含 ≥2 纯字母英文单词且带句尾标点或英文功能词；字段名/品牌名/
 *   单技术词天然豁免），与 9g/9h/9j「混入字形」检测互补拦截「整条还是英文」
 *
 * 支持语言必须与 src/i18n/config.ts locales 一致：zh / en / ja / ko / de / zh-TW。
 *
 * [INPUT] verify-i18n/settings-keys · namespace-keys · shell-contracts · locale-parity (POS: 各组检查，职责见 scripts/_ARCH.md)
 *         verify-i18n/context (POS: 共享上下文与支持语言)
 * [OUTPUT] 退出码 0（全部通过）/ 1（任一检查失败）与控制台报告
 * [POS] i18n 全量门禁入口：只做按序编排，不含检查实现。
 */

import { resolve, dirname } from 'path';
import { fileURLToPath } from 'url';
import { createContext, loadTranslations } from './verify-i18n/context.mjs';
import { verifyLocaleParity } from './verify-i18n/locale-parity.mjs';
import {
  verifyAgentConfigPanel,
  verifyArtifactsCenter,
  verifyBuiltinToolTexts,
  verifyCronBlueprint,
  verifyCronExecutionPolicy,
  verifyKanbanClosure,
} from './verify-i18n/namespace-keys.mjs';
import {
  readSettingsTabs,
  verifyDeveloperKeys,
  verifySettingsMenu,
  verifySettingsTabs,
} from './verify-i18n/settings-keys.mjs';
import { verifyHomeRouteShellContract, verifyShellDeferredNamespaceGate } from './verify-i18n/shell-contracts.mjs';

const rootDir = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const settingsTabs = readSettingsTabs(rootDir);
const ctx = createContext(rootDir);

console.log('🔍 开始验证翻译完整性...\n');

loadTranslations(ctx);

console.log('\n');

verifyShellDeferredNamespaceGate(ctx);

console.log('\n');

verifySettingsTabs(ctx, settingsTabs);
verifySettingsMenu(ctx, settingsTabs);
verifyDeveloperKeys(ctx);
verifyAgentConfigPanel(ctx);
verifyKanbanClosure(ctx);
verifyArtifactsCenter(ctx);
verifyCronBlueprint(ctx);
verifyCronExecutionPolicy(ctx);
verifyBuiltinToolTexts(ctx);
verifyHomeRouteShellContract(ctx);
verifyLocaleParity(ctx);

// 最终结果
console.log('\n' + '='.repeat(50));
if (ctx.hasErrors) {
  console.error('❌ 验证失败！发现翻译完整性问题。');
  process.exit(1);
} else {
  console.log('✅ 验证通过！所有翻译文件完整且一致。');
  process.exit(0);
}
