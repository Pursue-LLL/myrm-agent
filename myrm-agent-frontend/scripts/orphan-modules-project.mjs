/**
 * 项目树的孤儿扫描（读文件系统，把文件读成 `orphan-modules-scan.ts` 的入参）：孤儿门禁 `check-orphan-modules.mjs`
 * 与硬编码文案门禁 `check-hardcoded-copy.mjs` 共用，两道门禁对「哪些模块从产品入口不可达」只有这一个口径。
 */
import { readdirSync, readFileSync } from 'node:fs';
import { extname, join, relative, sep } from 'node:path';

import { findOrphanModules } from './orphan-modules-scan.ts';
import { walkSourceFiles } from './source-files.mjs';

const SOURCE_EXTENSIONS = new Set(['.ts', '.tsx']);
/** `src/` 之外会引用 `src/` 模块的文件扩展名。 */
export const CONSUMER_EXTENSIONS = new Set(['.ts', '.mjs', '.cjs', '.js']);

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

/**
 * 扫描 `root` 下的项目树（工作区或 merge-base 的对照树）。
 * @param {string} root 前端项目根（含 `src/` 与 `scripts/`）
 * @returns {import('./orphan-modules-scan.ts').OrphanScanResult} 候选模块数与孤儿路径（相对项目根的 posix 路径）
 */
export function scanProject(root) {
  return findOrphanModules({
    srcFiles: [...walkSourceFiles(join(root, 'src'), SOURCE_EXTENSIONS, { includeTests: true })].map((file) =>
      toSourceFile(root, file),
    ),
    consumerFiles: [...consumerPaths(root)].map((file) => toSourceFile(root, file)),
  });
}
