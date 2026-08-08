/**
 * [INPUT] scripts/i18n-shell-allowlist.json (POS: 翻译壳检测豁免清单)
 * [OUTPUT] walkTypes / resolvePath / isLegitSameValue / loadShellAllowlist / collectTranslationShells
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

/** 与 verify-i18n.mjs 壳检测豁免规则保持同步。 */
export function isLegitSameValue(value) {
  if (!value) return true;
  if (value.length < 3) return true;
  if (/[\u0080-\uFFFF]/.test(value)) return true;
  if (/[{}$%^]/.test(value)) return true;
  if (/https?:\/\//.test(value) || value.includes('/') || value.includes('\\')) return true;
  if (/^[\d\s.,-]+$/.test(value)) return true;
  if (value.includes('...')) return true;
  if (!value.includes(' ') && /^[A-Z0-9][A-Z0-9._-]*$/.test(value)) return true;
  return false;
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
