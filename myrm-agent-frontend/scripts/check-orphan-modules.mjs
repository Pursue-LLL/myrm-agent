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
 * 默认是绝对口径（全树零孤儿，`pretest` 使用）。`--base REV` 切到 diff 口径（CI 的 PR 门禁使用）：
 * 只有相对 HEAD 与 REV 的 merge-base 新出现的孤儿才失败，见 `orphan-modules-base.ts`。对照树无法确定时 fail-closed。
 *
 * 反向自检：候选模块数为 0 说明路径或解析器失效，直接失败而不是静默通过。
 *
 * 运行：bun scripts/check-orphan-modules.mjs [--base origin/main]
 * 退出码：0 = 无孤儿；1 = 发现孤儿或自检失败；2 = --base 指定的对照无法确定
 */
import { mkdtempSync, readdirSync, readFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, extname, join, relative, resolve, sep } from 'node:path';
import { fileURLToPath } from 'node:url';
import { parseArgs } from 'node:util';

import { BaseUnavailableError, introducedOrphans, materializeBase } from './orphan-modules-base.ts';
import { findOrphanModules } from './orphan-modules-scan.ts';
import { walkSourceFiles } from './source-files.mjs';

const rootDir = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const SOURCE_EXTENSIONS = new Set(['.ts', '.tsx']);
const CONSUMER_EXTENSIONS = new Set(['.ts', '.mjs', '.cjs', '.js']);
const BASE_DIRECTORIES = ['src', 'scripts'];
const EXIT_BASE_UNAVAILABLE = 2;

function fail(message, code = 1) {
  console.error(`[orphan-gate] ${message}`);
  process.exit(code);
}

function toSourceFile(root, file) {
  return { path: relative(root, file).split(sep).join('/'), source: readFileSync(file, 'utf8') };
}

/** `src/` 之外会引用 `src/` 模块的文件：项目根的构建配置与 `scripts/`（测试除外）。 */
function* consumerPaths(root) {
  for (const entry of readdirSync(root, { withFileTypes: true })) {
    if (entry.isFile() && CONSUMER_EXTENSIONS.has(extname(entry.name)) && !entry.name.endsWith('.d.ts')) {
      yield join(root, entry.name);
    }
  }
  yield* walkSourceFiles(join(root, 'scripts'), CONSUMER_EXTENSIONS);
}

/** 扫描 `root` 下的项目树（工作区或 merge-base 的对照树）。 */
function scanProject(root) {
  return findOrphanModules({
    srcFiles: [...walkSourceFiles(join(root, 'src'), SOURCE_EXTENSIONS, { includeTests: true })].map((file) =>
      toSourceFile(root, file),
    ),
    consumerFiles: [...consumerPaths(root)].map((file) => toSourceFile(root, file)),
  });
}

/** merge-base 上的孤儿集合；取不到或扫不出模块都算对照无法确定。 */
function baseOrphans(rev) {
  const scratch = mkdtempSync(join(tmpdir(), 'orphan-base-'));
  try {
    const sha = materializeBase({
      projectRoot: rootDir,
      rev,
      destination: scratch,
      directories: BASE_DIRECTORIES,
      rootExtensions: CONSUMER_EXTENSIONS,
    });
    const result = scanProject(scratch);
    if (result.scanned === 0) {
      throw new BaseUnavailableError(`对照树 ${sha.slice(0, 10)} 的 src/ 没有可扫描的模块`);
    }
    return { sha, orphans: result.orphans };
  } finally {
    rmSync(scratch, { recursive: true, force: true });
  }
}

let options;
try {
  ({ values: options } = parseArgs({ options: { base: { type: 'string' } } }));
} catch (error) {
  fail(`参数错误: ${error.message}`);
}

let result;
try {
  result = scanProject(rootDir);
} catch (error) {
  fail(`扫描失败: ${error.message}`);
}

if (result.scanned === 0) {
  fail('自检失败：未在 src/ 扫描到任何模块，路径或扩展名配置可能已失效——拒绝静默通过。');
}

let failing = result.orphans;
let baseSha;
if (options.base) {
  try {
    const existing = baseOrphans(options.base);
    baseSha = existing.sha;
    failing = introducedOrphans(result.orphans, existing.orphans);
  } catch (error) {
    if (!(error instanceof BaseUnavailableError)) {
      throw error;
    }
    fail(`无法对照 --base ${options.base}: ${error.message}`, EXIT_BASE_UNAVAILABLE);
  }
}

if (failing.length > 0) {
  const verdict = baseSha
    ? '本次改动之后成为孤儿（新增未接入，或切断了最后一个消费者）'
    : '孤儿模块（从产品入口不可达）';
  console.error(`[orphan-gate] ${failing.length} 个${verdict}：`);
  for (const orphan of failing) {
    console.error(`    - ${orphan}`);
  }
  fail('\n处理方式：接入产品入口；或连同测试、_ARCH.md 文档行、i18n 键一起删除。没有基线与豁免标记。');
}

console.log(
  baseSha
    ? `[orphan-gate] OK：相对 merge-base ${baseSha.slice(0, 10)} 没有新增孤儿（存量孤儿 ${result.orphans.length} 个不计入）。`
    : `[orphan-gate] OK：${result.scanned} 个模块均可从产品入口到达，无孤儿。`,
);
