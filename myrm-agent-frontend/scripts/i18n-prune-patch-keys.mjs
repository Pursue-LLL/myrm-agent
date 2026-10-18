#!/usr/bin/env node
/**
 * 修剪 translation-patches 里 en SSOT 已不存在的键。
 *
 * [INPUT] locales/en.json（key SSOT）+ scripts/translation-patches/<locale>/*.json
 * [OUTPUT] 就地删除「点分路径在 en 里不是叶子」的补丁叶子；整段变空的子树一并删除。
 * [POS] `i18n-patch-apply.mjs` 结构性破坏校验的配套清理工具：门禁只报告，这里负责把补丁源修回与 en 一致。
 *
 * 补丁里 en 不存在的键写进 locale 就是孤儿键（`verify:i18n` 的 key parity 会拒绝），
 * 在补丁源上删掉比在应用时拦截更接近问题根因。
 *
 * 用法：node scripts/i18n-prune-patch-keys.mjs [--locale ko] [--check]
 *   --check  只报告，不写回；有需要修剪的键时退出码为 1（供 CI/pre-commit 使用）
 */

import { readdirSync, readFileSync, statSync, writeFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const rootDir = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const args = process.argv.slice(2);
const checkOnly = args.includes('--check');
const localeIdx = args.indexOf('--locale');
const onlyLocale = localeIdx >= 0 ? args[localeIdx + 1] : undefined;

/** 叶子路径集合；数组与非对象叶子一律记为叶子。 */
function leafPaths(tree, prefix, out) {
  if (Array.isArray(tree) || tree === null || typeof tree !== 'object') {
    if (prefix) {
      out.add(prefix);
    }
    return out;
  }
  for (const [key, child] of Object.entries(tree)) {
    leafPaths(child, prefix ? `${prefix}.${key}` : key, out);
  }
  return out;
}

const enLeaves = leafPaths(JSON.parse(readFileSync(resolve(rootDir, 'locales/en.json'), 'utf-8')), '', new Set());
const patchRoot = resolve(rootDir, 'scripts/translation-patches');

/** 删除 en 里不是叶子的键；返回删除数。子树变空时整段摘除，因为空对象补丁没有意义。 */
function prune(node, prefix, removed) {
  for (const [key, value] of Object.entries(node)) {
    const here = prefix ? `${prefix}.${key}` : key;
    if (Array.isArray(value) || value === null || typeof value !== 'object') {
      if (!enLeaves.has(here)) {
        delete node[key];
        removed.push(here);
      }
      continue;
    }
    prune(value, here, removed);
    if (Object.keys(value).length === 0) {
      delete node[key];
    }
  }
}

const locales = readdirSync(patchRoot)
  .filter((name) => (onlyLocale === undefined || name === onlyLocale) && statSync(join(patchRoot, name)).isDirectory())
  .sort();
if (locales.length === 0) {
  console.error(`未找到补丁目录${onlyLocale ? `: ${onlyLocale}` : ''}`);
  process.exit(1);
}

let changedFiles = 0;
let totalRemoved = 0;
for (const locale of locales) {
  const dir = join(patchRoot, locale);
  for (const name of readdirSync(dir)
    .filter((f) => f.endsWith('.json'))
    .sort()) {
    const path = join(dir, name);
    const patch = JSON.parse(readFileSync(path, 'utf-8'));
    const removed = [];
    prune(patch, '', removed);
    if (removed.length === 0) {
      continue;
    }
    changedFiles += 1;
    totalRemoved += removed.length;
    console.log(`${locale}/${name}: 删除 ${removed.length} 个 en 不存在的键`);
    for (const key of removed.slice(0, 5)) {
      console.log(`    - ${key}`);
    }
    if (removed.length > 5) {
      console.log(`    … 另有 ${removed.length - 5} 个`);
    }
    if (!checkOnly) {
      writeFileSync(path, JSON.stringify(patch, null, 2) + '\n');
    }
  }
}

if (totalRemoved === 0) {
  console.log('✅ 所有补丁键都在 en SSOT 里。');
  process.exit(0);
}
if (checkOnly) {
  console.error(
    `\n❌ ${changedFiles} 个补丁文件里有 ${totalRemoved} 个 en 不存在的键；运行 node scripts/i18n-prune-patch-keys.mjs 清理。`,
  );
  process.exit(1);
}
console.log(`✅ 清理完成：${changedFiles} 个文件，共删除 ${totalRemoved} 个键。`);
