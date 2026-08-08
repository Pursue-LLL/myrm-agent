#!/usr/bin/env node
/**
 * [INPUT] locales/en.json + locales/<locale>.json (POS: 六语翻译 SSOT)
 *         scripts/i18n-shell-core.mjs (POS: 壳检测共享逻辑)
 *         scripts/i18n-shell-allowlist.json (POS: 壳检测豁免清单)
 * [OUTPUT] 剩余翻译壳清单（TSV 或 JSON，stdout 或 --out 文件）
 * [POS] 批量翻译工作流辅助脚本。按 verify-i18n 同款壳检测逻辑导出待翻译键清单。
 *
 * Usage:
 *   node scripts/i18n-dump-remaining.mjs <locale>
 *   node scripts/i18n-dump-remaining.mjs de --json --limit 250 --offset 0
 *   node scripts/i18n-dump-remaining.mjs de --stats
 */

import { readFileSync, writeFileSync } from 'fs';
import { resolve, dirname } from 'path';
import { fileURLToPath } from 'url';
import { collectTranslationShells, loadShellAllowlist } from './i18n-shell-core.mjs';

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

let allowlists;
try {
  allowlists = loadShellAllowlist(rootDir);
} catch (error) {
  const message = error instanceof Error ? error.message : String(error);
  console.error(`无法加载 i18n-shell-allowlist.json: ${message}`);
  process.exit(1);
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
const shells = collectTranslationShells(enData, localeData, allowlists);

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
