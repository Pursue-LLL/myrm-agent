/**
 * [INPUT] scripts/i18n-shell-allowlist.json (POS: 翻译壳检测豁免清单)
 * [OUTPUT] walkTypes / resolvePath / isLegitSameValue / isTranslationShell / loadShellAllowlist / collectTranslationShells
 * [POS] i18n 翻译壳检测共享逻辑。供 verify-i18n.mjs 与 i18n-dump-remaining.mjs 共用，防止 gate 口径漂移。
 */

import { readFileSync } from 'fs';
import { resolve, dirname } from 'path';
import { fileURLToPath } from 'url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const scriptsDir = resolve(__dirname);

export function walkTypes(obj, prefix, out) {
  if (Array.isArray(obj)) {
    out.set(prefix, 'array');
    return;
  }
  if (obj && typeof obj === 'object') {
    const keys = Object.keys(obj);
    if (keys.length === 0) {
      out.set(prefix, 'object');
      return;
    }
    for (const key of keys) {
      walkTypes(obj[key], prefix ? `${prefix}.${key}` : key, out);
    }
    return;
  }
  out.set(prefix, typeof obj);
}

export function resolvePath(obj, dottedPath) {
  let node = obj;
  for (const part of dottedPath.split('.')) {
    if (node == null || typeof node !== 'object') return undefined;
    node = node[part];
  }
  return node;
}

/**
 * 值是否可合法保持与英文一致（非翻译壳）。
 *
 * 判据按「值整体类型」判定：
 * - 含非 ASCII（已本地化）/ URL / 纯路径 / 邮箱 / 域名 → 合法保留；
 * - 无空格 token：全大写国际缩写（`MCP`/`FAQ`/`URL`）→ 合法；含非字母结构
 *   （`-`/`/`/`@`/`#`/数字等，如 `sk-...`、`spaces/xxxxx`、`@bot:matrix.org`）→ 合法；
 *   纯英文单词（`Active`/`Paused`）或纯单词+省略号（`Loading...`）→ 判壳；
 * - 去除 ICU 占位符后不再含英文实义词（≥2 字母）→ 纯格式模板（如 `{count} / {max}`）→ 合法；
 * - 其余含英文实义词的值 → 判为翻译壳（需翻译或由 allowlist 显式豁免）。
 * 仅豁免具体格式（URL/路径/邮箱/域名/纯 token/纯格式模板/全大写缩写），
 * 不含 `{}$%^`、`/`、`...` 等字符级一刀切豁免，避免「Loading...」「Task {taskId} resumed」
 * 等未翻译英文被漏检。
 */
export function isLegitSameValue(value) {
  if (!value || value.length < 3) return true;
  if (/[\u0080-\uFFFF]/.test(value)) return true;
  if (/https?:\/\//.test(value)) return true;
  if (/^\/[^\s]*$/.test(value)) return true;
  if (/^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$/.test(value)) return true;
  if (/^[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)+$/.test(value)) return true;
  if (!value.includes(' ')) {
    // 全大写缩写（MCP/FAQ/URL 等国际通用缩写）→ 合法保留
    if (/^[A-Z]{2,}$/.test(value)) return true;
    // 纯字母单词（Active/Paused/TypeScript）→ 判壳
    if (/^[A-Za-z]+$/.test(value)) return false;
    if (value.endsWith('...')) {
      const core = value.slice(0, -3);
      return !/^[A-Za-z]+$/.test(core);
    }
    return true;
  }
  const stripped = value.replace(/\{[^{}]+\}/g, ' ').replace(/[.,;:!?()[\]/\\]/g, ' ');
  return !/[A-Za-z]{2,}/.test(stripped);
}

export function loadShellAllowlist(rootDir = resolve(scriptsDir, '..')) {
  const allowlist = JSON.parse(
    readFileSync(resolve(rootDir, 'scripts/i18n-shell-allowlist.json'), 'utf-8'),
  );
  return {
    allowedSameValues: new Set(allowlist.allowedSameValues || []),
    allowedSameKeys: new Set(allowlist.allowedSameKeys || []),
  };
}

export function isTranslationShell(key, enValue, localeValue, allowlists) {
  if (typeof enValue !== 'string' || typeof localeValue !== 'string') return false;
  if (localeValue !== enValue || enValue.length <= 2) return false;
  if (isLegitSameValue(enValue)) return false;
  if (allowlists.allowedSameValues.has(enValue)) return false;
  if (allowlists.allowedSameKeys.has(key)) return false;
  return true;
}

export function collectTranslationShells(enData, localeData, allowlists) {
  const enTypes = new Map();
  walkTypes(enData, '', enTypes);
  const shells = [];

  const visit = (key, enValue, localeValue) => {
    if (Array.isArray(enValue)) {
      enValue.forEach((item, index) => {
        const localeItem = Array.isArray(localeValue) ? localeValue[index] : undefined;
        if (typeof item === 'string' && typeof localeItem === 'string') {
          visit(`${key}[${index}]`, item, localeItem);
        }
      });
      return;
    }
    if (isTranslationShell(key, enValue, localeValue, allowlists)) {
      shells.push({ key, en: enValue });
    }
  };

  for (const key of enTypes.keys()) {
    if (!key) continue;
    const enValue = resolvePath(enData, key);
    const localeValue = resolvePath(localeData, key);
    if (enValue === undefined || localeValue === undefined) continue;
    visit(key, enValue, localeValue);
  }

  shells.sort((a, b) => a.key.localeCompare(b.key));
  return shells;
}
