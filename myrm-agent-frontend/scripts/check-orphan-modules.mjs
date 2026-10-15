#!/usr/bin/env node
/**
 * 孤儿模块门禁：`src/` 下从产品入口不可达的模块一律拦截，零容忍，没有基线、没有豁免标记。
 *
 * 背景：单元测试 import 被测文件，一个从入口不可达的组件它的测试照样绿——测试绿不等于代码活着。
 * 本门禁补上这个结构性盲区；判定口径（入口、可达闭包、barrel、测试排除）见 `orphan-modules-scan.ts`。
 *
 * 处理方式只有两种：接入产品入口；或连同测试、`_ARCH.md` 文档行、i18n 键一起删除。
 * 不提供基线或豁免——存量豁免会让“暂时保留”变成永久保留。
 *
 * 反向自检：候选模块数为 0 说明路径或解析器失效，直接失败而不是静默通过。
 *
 * 运行：bun scripts/check-orphan-modules.mjs
 * 退出码：0 = 无孤儿；1 = 发现孤儿或自检失败
 */
import { readdirSync, readFileSync } from 'node:fs';
import { dirname, extname, join, relative, resolve, sep } from 'node:path';
import { fileURLToPath } from 'node:url';

import { findOrphanModules } from './orphan-modules-scan.ts';
import { walkSourceFiles } from './source-files.mjs';

const rootDir = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const SOURCE_EXTENSIONS = new Set(['.ts', '.tsx']);
const CONSUMER_EXTENSIONS = new Set(['.ts', '.mjs', '.cjs', '.js']);

function fail(message) {
  console.error(`[orphan-gate] ${message}`);
  process.exit(1);
}

function toSourceFile(file) {
  return { path: relative(rootDir, file).split(sep).join('/'), source: readFileSync(file, 'utf8') };
}

/** `src/` 之外会引用 `src/` 模块的文件：项目根的构建配置与 `scripts/`（测试除外）。 */
function* consumerPaths() {
  for (const entry of readdirSync(rootDir, { withFileTypes: true })) {
    if (entry.isFile() && CONSUMER_EXTENSIONS.has(extname(entry.name)) && !entry.name.endsWith('.d.ts')) {
      yield join(rootDir, entry.name);
    }
  }
  yield* walkSourceFiles(join(rootDir, 'scripts'), CONSUMER_EXTENSIONS);
}

let result;
try {
  result = findOrphanModules({
    srcFiles: [...walkSourceFiles(join(rootDir, 'src'), SOURCE_EXTENSIONS, { includeTests: true })].map(toSourceFile),
    consumerFiles: [...consumerPaths()].map(toSourceFile),
  });
} catch (error) {
  fail(`扫描失败: ${error.message}`);
}

if (result.scanned === 0) {
  fail('自检失败：未在 src/ 扫描到任何模块，路径或扩展名配置可能已失效——拒绝静默通过。');
}

if (result.orphans.length > 0) {
  console.error(`[orphan-gate] ${result.orphans.length} 个孤儿模块（从产品入口不可达）：`);
  for (const orphan of result.orphans) {
    console.error(`    - ${orphan}`);
  }
  fail('\n处理方式：接入产品入口；或连同测试、_ARCH.md 文档行、i18n 键一起删除。没有基线与豁免标记。');
}

console.log(`[orphan-gate] OK：${result.scanned} 个模块均可从产品入口到达，无孤儿。`);
