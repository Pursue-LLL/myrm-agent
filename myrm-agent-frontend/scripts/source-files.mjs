/**
 * 前端源码遍历：静态门禁脚本共用。剪掉依赖与构建产物目录；默认排除测试文件——
 * 测试里会有意写出被门禁禁止的写法、用字面量文案作断言，不属于门禁要管的生产代码。
 */
import { readdirSync } from 'node:fs';
import { extname, join } from 'node:path';

const PRUNE_DIRS = new Set(['node_modules', '.next', 'dist']);
const TEST_PATH = /(?:^|[\\/])__tests__[\\/]|\.test\.tsx?$/;

/**
 * @param {string} dir 起始目录
 * @param {ReadonlySet<string>} extensions 带点的扩展名集合，如 `new Set(['.tsx'])`
 * @param {{ includeTests?: boolean }} [options] `includeTests` 为真时不排除测试文件（统计口径需覆盖测试时使用）
 * @returns {Generator<string>} 命中扩展名的源码文件绝对路径
 */
export function* walkSourceFiles(dir, extensions, { includeTests = false } = {}) {
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    if (PRUNE_DIRS.has(entry.name)) {
      continue;
    }
    const full = join(dir, entry.name);
    if (entry.isDirectory()) {
      yield* walkSourceFiles(full, extensions, { includeTests });
    } else if (extensions.has(extname(entry.name)) && (includeTests || !TEST_PATH.test(full))) {
      yield full;
    }
  }
}
