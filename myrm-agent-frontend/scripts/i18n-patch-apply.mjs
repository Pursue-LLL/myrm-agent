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
 * 补丁是「内容补齐」：只填缺失键与仍是英文 SSOT 的未翻译键。目标语言里已有的独立译法不会被覆盖——
 * 补丁是某一时刻的翻译快照，重放它若覆盖后来改好的文案，等于把已本地化的界面悄悄退回英文。
 * 每个补丁叶子必须是 `locales/en.json` 里真实存在的键，且不得把已存在的对象子树替换成单条文案；
 * 违反其一即整体失败，`locales/<locale>.json` 不写入。
 *
 * 应用完成后打印各补丁文件的贡献计数（填充 / 已存在未改动）与逐条跳过原因，供校验。
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

/**
 * 补丁是「只补不删」的内容补齐工具，每个补丁叶子都必须是 en SSOT 里真实存在的键：
 * en 是唯一 key SSOT，写进补丁的键若只在某个语言里成立，应用后就成了该语言的孤儿键（`verify:i18n` 的 key parity 会拒绝）。
 * 同样不得把已存在的对象子树替换成单条文案——那会静默丢掉整棵已翻译子树。两种情况都直接失败，
 * 由应用器当场报告，而不是「应用成功」之后把损害留给下游门禁去发现。
 */
function leafPaths(node, prefix, out) {
  if (Array.isArray(node) || node === null || typeof node !== 'object') {
    if (prefix) {
      out.add(prefix);
    }
    return out;
  }
  for (const [key, child] of Object.entries(node)) {
    leafPaths(child, prefix ? `${prefix}.${key}` : key, out);
  }
  return out;
}

/**
 * en SSOT 的每个叶子，作为 `点分路径 -> 值`。
 * 应用器据此区分「目标语言里仍是英文 SSOT」与「已有独立译文」：前者是补丁要补的，后者不能用旧快照覆盖。
 */
function collectEnLeaves(node, prefix, out) {
  if (Array.isArray(node) || node === null || typeof node !== 'object') {
    if (prefix) {
      out.set(prefix, node);
    }
    return out;
  }
  for (const [key, child] of Object.entries(node)) {
    collectEnLeaves(child, prefix ? `${prefix}.${key}` : key, out);
  }
  return out;
}

const enLeaves = collectEnLeaves(JSON.parse(readFileSync(resolve(rootDir, 'locales/en.json'), 'utf-8')), '', new Map());

const violations = [];

function applyPatch(target, patch, count, path) {
  for (const [key, value] of Object.entries(patch)) {
    const here = path ? `${path}.${key}` : key;
    const existing = target[key];
    const isPatchArray = Array.isArray(value);
    const isPatchLeaf = value === null || typeof value !== 'object' || isPatchArray;
    if (isPatchLeaf) {
      if (existing !== undefined && typeof existing === 'object' && existing !== null && !Array.isArray(existing)) {
        violations.push(`${here}: patch leaf would replace the existing object subtree`);
        continue;
      }
      if (!enLeaves.has(here)) {
        violations.push(`${here}: key is absent from locales/en.json (the key SSOT)`);
        continue;
      }
      if (existing === undefined) {
        target[key] = value;
        count.added += 1;
      } else if (existing === enLeaves.get(here) && existing !== value) {
        // Still the English SSOT value: an untranslated key this patch exists to fill.
        target[key] = value;
        count.filled += 1;
      } else {
        count.kept += 1;
      }
    } else if (existing && typeof existing === 'object' && !Array.isArray(existing)) {
      applyPatch(existing, value, count, here);
    } else {
      const unknown = [...leafPaths(value, here, new Set())].filter((leaf) => !enLeaves.has(leaf));
      if (unknown.length > 0) {
        violations.push(`${unknown[0]}: key is absent from locales/en.json (the key SSOT)`);
        continue;
      }
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

let totalFilled = 0;
let totalAdded = 0;
let totalKept = 0;
for (const name of files) {
  const patch = JSON.parse(readFileSync(join(patchDir, name), 'utf-8'));
  const count = { filled: 0, added: 0, kept: 0 };
  applyPatch(localeData, patch, count, '');
  totalFilled += count.filled;
  totalAdded += count.added;
  totalKept += count.kept;
  console.log(`  ${name}: 填充未翻译 ${count.filled} / 新增 ${count.added} / 保留已有译文 ${count.kept}`);
}

if (violations.length > 0) {
  console.error(
    `\n❌ ${locale}.json 未写入：补丁里有 ${violations.length} 处结构性破坏，写入会丢掉已翻译内容或加入孤儿键。`,
  );
  for (const violation of violations) {
    console.error(`  - ${violation}`);
  }
  console.error(
    '\n处理方式：删掉补丁里 en SSOT 不存在的键（它们不是文案）；' +
      '若补丁把 `cron.schedule` 这类对象写成了单条字符串，改用对应的叶子键路径（如 `cron.schedule.title`）。',
  );
  process.exit(1);
}

writeFileSync(localeFile, JSON.stringify(localeData, null, 2) + '\n');
console.log(
  `✅ ${locale}.json 已更新：填充未翻译 ${totalFilled} 条 / 新增 ${totalAdded} 条 / 保留已有译文 ${totalKept} 条`,
);
