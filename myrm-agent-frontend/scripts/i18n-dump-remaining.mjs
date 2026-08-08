#!/usr/bin/env node
/**
 * Export remaining translation shells for a locale using verify-i18n gate logic.
 *
 * Usage:
 *   node scripts/i18n-dump-remaining.mjs <locale>
 *   node scripts/i18n-dump-remaining.mjs de --json --limit 250 --offset 0
 *   node scripts/i18n-dump-remaining.mjs de --stats
 *
 * Output (default TSV): dottedKey<TAB>enValue
 * With --json: [{ "key", "en" }, ...]
 */

import { readFileSync, writeFileSync } from 'fs';
import { resolve, dirname } from 'path';
import { fileURLToPath } from 'url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const rootDir = resolve(__dirname, '..');

const locale = process.argv[2];
if (!locale || locale.startsWith('-')) {
  console.error('用法: node scripts/i18n-dump-remaining.mjs <locale> [--json] [--limit N] [--offset N] [--stats] [--out FILE]');
  process.exit(1);
}

const args = process.argv.slice(3);
const asJson = args.includes('--json');
const statsOnly = args.includes('--stats');
const limitIdx = args.indexOf('--limit');
const offsetIdx = args.indexOf('--offset');
const outIdx = args.indexOf('--out');
const limit = limitIdx >= 0 ? Number(args[limitIdx + 1]) : undefined;
const offset = offsetIdx >= 0 ? Number(args[offsetIdx + 1]) : 0;
const outFile = outIdx >= 0 ? args[outIdx + 1] : undefined;

let ALLOWED_SAME_VALUES = new Set();
let ALLOWED_SAME_KEYS = new Set();
try {
  const allowlist = JSON.parse(
    readFileSync(resolve(rootDir, 'scripts/i18n-shell-allowlist.json'), 'utf-8'),
  );
  ALLOWED_SAME_VALUES = new Set(allowlist.allowedSameValues || []);
  ALLOWED_SAME_KEYS = new Set(allowlist.allowedSameKeys || []);
} catch (error) {
  console.error(`无法加载 i18n-shell-allowlist.json: ${error.message}`);
  process.exit(1);
}

function walkTypes(obj, prefix, out) {
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

function resolvePath(obj, dottedPath) {
  let node = obj;
  for (const part of dottedPath.split('.')) {
    if (node == null || typeof node !== 'object') return undefined;
    node = node[part];
  }
  return node;
}

function isLegitSameValue(value) {
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

function isShell(key, enValue, localeValue) {
  if (typeof enValue !== 'string' || typeof localeValue !== 'string') return false;
  if (localeValue !== enValue || enValue.length <= 2) return false;
  if (isLegitSameValue(enValue)) return false;
  if (ALLOWED_SAME_VALUES.has(enValue)) return false;
  if (ALLOWED_SAME_KEYS.has(key)) return false;
  return true;
}

function collectShells(enData, localeData) {
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
    if (typeof enValue === 'string' && typeof localeValue === 'string') {
      if (isShell(key, enValue, localeValue)) {
        shells.push({ key, en: enValue });
      }
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

function namespaceStats(shells) {
  const counts = new Map();
  for (const { key } of shells) {
    const ns = key.split('.')[0];
    counts.set(ns, (counts.get(ns) || 0) + 1);
  }
  return [...counts.entries()].sort((a, b) => b[1] - a[1]);
}

const enData = JSON.parse(readFileSync(resolve(rootDir, 'locales/en.json'), 'utf-8'));
const localeData = JSON.parse(readFileSync(resolve(rootDir, `locales/${locale}.json`), 'utf-8'));
const shells = collectShells(enData, localeData);

if (statsOnly) {
  console.log(`${locale}.json shells: ${shells.length}`);
  for (const [ns, count] of namespaceStats(shells).slice(0, 15)) {
    console.log(`  ${ns}: ${count}`);
  }
  process.exit(0);
}

const slice = shells.slice(offset, limit === undefined ? undefined : offset + limit);

if (asJson) {
  const payload = JSON.stringify(slice, null, 2);
  if (outFile) writeFileSync(outFile, payload + '\n');
  else console.log(payload);
} else {
  const lines = slice.map(({ key, en }) => `${key}\t${en.replace(/\t/g, ' ')}`);
  const payload = lines.join('\n') + (lines.length ? '\n' : '');
  if (outFile) writeFileSync(outFile, payload);
  else process.stdout.write(payload);
}

if (!outFile) {
  console.error(`# ${locale} shells total=${shells.length} exported=${slice.length} offset=${offset}`);
}
