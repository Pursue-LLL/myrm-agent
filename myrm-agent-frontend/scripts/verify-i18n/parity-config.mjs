/**
 * [INPUT] i18n-shell-core::loadShellAllowlist (POS: 翻译壳检测共享逻辑)
 *         scripts/i18n-shell-allowlist.json (POS: 壳/双语豁免)
 * [OUTPUT] loadParityConfig / EN_PURITY_ALLOWED_KEYS
 * [POS] verify-i18n 全量门禁（验证 9）的配置装载与豁免键：壳/双语豁免清单；任何装载失败都置 hasErrors（fail-safe），不静默放行。
 */

import { readFileSync } from 'fs';
import { resolve } from 'path';
import { loadShellAllowlist } from '../i18n-shell-core.mjs';

/** en（SSOT）纯净性豁免键：语言名本身即目标语言文字。 */
export const EN_PURITY_ALLOWED_KEYS = new Set(['settings.languageOptions.chinese']);

/**
 * 装载壳检测 allowlist。
 * 按步骤逐项赋值：中途失败时已装载的部分保留、其余保持空集合（与失败位置一致的降级口径）。
 *
 * @returns {{
 *   shellAllowlists: { allowedSameValues: Set<string>, allowedSameKeys: Set<string> },
 *   allowedMixedValues: Set<string>,
 *   allowedMixedKeys: Set<string>,
 * }}
 */
export function loadParityConfig(ctx) {
  const { rootDir } = ctx;
  const config = {
    shellAllowlists: { allowedSameValues: new Set(), allowedSameKeys: new Set() },
    allowedMixedValues: new Set(),
    allowedMixedKeys: new Set(),
  };
  try {
    config.shellAllowlists = loadShellAllowlist(rootDir);
    const allowlist = JSON.parse(readFileSync(resolve(rootDir, 'scripts/i18n-shell-allowlist.json'), 'utf-8'));
    config.allowedMixedValues = new Set(allowlist.allowedMixedValues || []);
    config.allowedMixedKeys = new Set(allowlist.allowedMixedKeys || []);
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    console.error(`  ❌ 无法加载 i18n allowlist: ${message}`);
    ctx.hasErrors = true;
  }
  return config;
}
