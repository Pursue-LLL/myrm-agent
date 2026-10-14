/**
 * 前端源码遍历：静态门禁脚本共用。剪掉依赖与构建产物目录，并排除测试文件——
 * 测试里会引用旧写法、字面量文案作断言，不属于门禁要管的生产代码。
 */
import { readdirSync } from 'node:fs';
import { extname, join } from 'node:path';

const PRUNE_DIRS = new Set(['node_modules', '.next', 'dist']);
const TEST_PATH = /(?:^|[\\/])__tests__[\\/]|\.test\.tsx?$/;

/**
 * @param {string} dir 起始目录
 * @param {ReadonlySet<string>} extensions 带点的扩展名集合，如 `new Set(['.tsx'])`
 * @returns {Generator<string>} 命中扩展名的非测试源码文件绝对路径
 */
export function* walkSourceFiles(dir, extensions) {
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    if (PRUNE_DIRS.has(entry.name)) {
      continue;
    }
    const full = join(dir, entry.name);
    if (entry.isDirectory()) {
      yield* walkSourceFiles(full, extensions);
    } else if (extensions.has(extname(entry.name)) && !TEST_PATH.test(full)) {
      yield full;
    }
  }
}
