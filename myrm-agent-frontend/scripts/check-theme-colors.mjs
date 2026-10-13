#!/usr/bin/env node
/**
 * 主题色写法门禁：`src/` 下的 ts / tsx / css 把主题变量包进 `hsl()` / `rgb()` 等颜色函数即失败（零容忍）。
 *
 * 背景与判定规则见 `theme-color-scan.ts`：这类写法不报错，只会让描边、填充、阴影静默失效，
 * 单测与 jsdom 都看不见，所以必须在静态阶段拦住。测试文件不扫描（测试里会引用旧写法作说明）。
 *
 * 反向自检：扫描文件数为 0 时直接失败，而不是静默通过。
 * 前提自检：`globals.css` 的 `--primary` 不是完整颜色时直接失败（变量若改成通道三元组，包 `hsl()` 反而是对的，
 * 规则必须先改，不能继续拦合法写法）。
 *
 * 运行：bun scripts/check-theme-colors.mjs
 * 退出码：0 = 无违规；1 = 有违规 / 自检失败
 */

import { readdirSync, readFileSync } from 'node:fs';
import { dirname, extname, join, relative, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import { findWrappedThemeColorSites, isCompleteColorValue } from './theme-color-scan.ts';

const rootDir = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const srcDir = join(rootDir, 'src');
const globalsCss = join(srcDir, 'app', 'globals.css');
const SOURCE_EXTENSIONS = new Set(['.ts', '.tsx', '.css']);
const PRUNE_DIRS = new Set(['node_modules', '.next', 'dist']);
const TEST_PATH = /(?:^|[\\/])__tests__[\\/]|\.test\.tsx?$/;

function* walk(dir) {
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    if (PRUNE_DIRS.has(entry.name)) {
      continue;
    }
    const full = join(dir, entry.name);
    if (entry.isDirectory()) {
      yield* walk(full);
    } else if (SOURCE_EXTENSIONS.has(extname(entry.name)) && !TEST_PATH.test(full)) {
      yield full;
    }
  }
}

// 前提自检：规则只在“主题变量是完整颜色”时成立，否则宁可失败也不误拦合法写法。
const primary = /--primary:\s*([^;]+);/.exec(readFileSync(globalsCss, 'utf8'))?.[1];
if (primary === undefined || !isCompleteColorValue(primary)) {
  console.error(
    `[theme-colors] 前提失效：globals.css 的 --primary 不是完整颜色（${primary ?? '未找到'}）。` +
      '请先更新 scripts/theme-color-scan.ts 的判定规则，再改主题变量格式。',
  );
  process.exit(1);
}

let scannedFiles = 0;
const violations = [];
for (const file of walk(srcDir)) {
  scannedFiles += 1;
  for (const { line, text } of findWrappedThemeColorSites(readFileSync(file, 'utf8'))) {
    violations.push(`${relative(rootDir, file)}:${line}  ${text}`);
  }
}

if (scannedFiles === 0) {
  console.error('[theme-colors] 自检失败：未扫描到任何源码文件，路径可能已失效——拒绝静默通过。');
  process.exit(1);
}

if (violations.length > 0) {
  console.error(
    `[theme-colors] 发现 ${violations.length} 处把主题变量包进颜色函数的写法（变量里已是完整颜色，整条声明会静默失效）：`,
  );
  for (const violation of violations) {
    console.error(`  ${violation}`);
  }
  console.error(
    '\n处理方式：直接写 `var(--primary)`；要透明度用 `color-mix(in srgb, var(--primary) 20%, transparent)`，' +
      'Tailwind 类里用 `shadow-primary/20` 等透明度修饰符。',
  );
  process.exit(1);
}

console.log(`[theme-colors] 通过：扫描 ${scannedFiles} 个文件，无主题变量被包进颜色函数。`);
