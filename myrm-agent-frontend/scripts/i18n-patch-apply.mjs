#!/usr/bin/env node
/**
 * i18n 内容补齐补丁应用器。
 *
 * 用法：node scripts/i18n-patch-apply.mjs <locale>
 *
 * 将 scripts/translation-patches/<locale>/*.json 中的补丁树深度合并进
 * locales/<locale>.json，然后写回（2 空格缩进 + 末尾换行，与仓库格式一致）。
 *
 * 补丁文件格式：与 locale 同构的嵌套 JSON 树，仅需包含要新增/替换的子树。
 * 数组类型键不递归合并，仅当目标键尚不存在时整段插入。
 *
 * 应用完成后打印各补丁文件的贡献计数，供校验。
 */

import { readFileSync, readdirSync, statSync, writeFileSync } from 'fs';
import { resolve, dirname, join } from 'path';
import { fileURLToPath } from 'url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const rootDir = resolve(__dirname, '..');

const locale = process.argv[2];
if (!locale) {
  console.error('用法: node scripts/i18n-patch-apply.mjs <locale>');
  process.exit(1);
}

const localeFile = resolve(rootDir, `locales/${locale}.json`);
const patchDir = resolve(rootDir, `scripts/translation-patches/${locale}`);

if (!statSync(localeFile).isFile()) {
  console.error(`缺少 locale 文件: ${localeFile}`);
  process.exit(1);
}

if (!statSync(patchDir).isDirectory()) {
  console.error(`缺少补丁目录: ${patchDir}`);
  process.exit(1);
}

const localeData = JSON.parse(readFileSync(localeFile, 'utf-8'));

function applyPatch(target, patch, count) {
  for (const [key, value] of Object.entries(patch)) {
    const existing = target[key];
    const isPatchArray = Array.isArray(value);
    const isPatchLeaf = value === null || typeof value !== 'object' || isPatchArray;
    if (isPatchLeaf) {
      if (existing !== value) {
        target[key] = value;
        count.applied += 1;
      }
    } else if (existing && typeof existing === 'object' && !Array.isArray(existing)) {
      applyPatch(existing, value, count);
    } else {
      target[key] = structuredClone(value);
      count.added += 1;
    }
  }
}

const files = readdirSync(patchDir)
  .filter((name) => name.endsWith('.json'))
  .sort();

if (files.length === 0) {
  console.log(`补丁目录为空: ${patchDir}`);
  process.exit(0);
}

let totalApplied = 0;
let totalAdded = 0;
for (const name of files) {
  const patch = JSON.parse(readFileSync(join(patchDir, name), 'utf-8'));
  const count = { applied: 0, added: 0 };
  applyPatch(localeData, patch, count);
  totalApplied += count.applied;
  totalAdded += count.added;
  console.log(`  ${name}: 替换 ${count.applied} / 新增 ${count.added}`);
}

writeFileSync(localeFile, JSON.stringify(localeData, null, 2) + '\n');
console.log(`✅ ${locale}.json 已更新：替换 ${totalApplied} 条 / 新增 ${totalAdded} 条`);
