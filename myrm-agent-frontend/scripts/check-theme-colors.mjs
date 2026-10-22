#!/usr/bin/env node
/**
 * 主题色写法门禁（零容忍），`src/` 下的 ts / tsx / css 出现以下任一写法即失败：
 * 1. 把主题变量包进 `hsl()` / `rgb()` 等颜色函数；
 * 2. 使用 `globals.css` 未声明 `--color-*` 的语义色工具类（`text-warning`、`bg-success/10` …）。
 *
 * 背景与判定规则见 `theme-color-scan.ts`：这两类写法都不报错，只会让描边、填充、阴影、底色静默失效，
 * 单测与 jsdom 都看不见，所以必须在静态阶段拦住。测试文件不扫描（测试里会引用旧写法作说明）。
 *
 * 反向自检：扫描文件数为 0 时直接失败，而不是静默通过。
 * 前提自检：`globals.css` 的 `--primary` 不是完整颜色时直接失败（变量若改成通道三元组，包 `hsl()` 反而是对的，
 * 规则必须先改，不能继续拦合法写法）。
 *
 * 运行：bun scripts/check-theme-colors.mjs
 * 退出码：0 = 无违规；1 = 有违规 / 自检失败
 */

import { readFileSync } from 'node:fs';
import { dirname, join, relative, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import { walkSourceFiles } from './source-files.mjs';
import {
  findUndefinedSemanticColorSites,
  findWrappedThemeColorSites,
  isCompleteColorValue,
  parseDeclaredColorTokens,
} from './theme-color-scan.ts';

const rootDir = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const srcDir = join(rootDir, 'src');
const globalsCssPath = join(srcDir, 'app', 'globals.css');
const SOURCE_EXTENSIONS = new Set(['.ts', '.tsx', '.css']);

// 前提自检：规则只在“主题变量是完整颜色”时成立，否则宁可失败也不误拦合法写法。
const globalsCss = readFileSync(globalsCssPath, 'utf8');
const primary = /--primary:\s*([^;]+);/.exec(globalsCss)?.[1];
if (primary === undefined || !isCompleteColorValue(primary)) {
  console.error(
    `[theme-colors] 前提失效：globals.css 的 --primary 不是完整颜色（${primary ?? '未找到'}）。` +
      '请先更新 scripts/theme-color-scan.ts 的判定规则，再改主题变量格式。',
  );
  process.exit(1);
}

const declaredColorTokens = parseDeclaredColorTokens(globalsCss);

let scannedFiles = 0;
const violations = [];
const undefinedTokenViolations = [];
for (const file of walkSourceFiles(srcDir, SOURCE_EXTENSIONS)) {
  scannedFiles += 1;
  const source = readFileSync(file, 'utf8');
  const where = relative(rootDir, file);
  for (const { line, text } of findWrappedThemeColorSites(source)) {
    violations.push(`${where}:${line}  ${text}`);
  }
  for (const { line, text, token } of findUndefinedSemanticColorSites(source, declaredColorTokens)) {
    undefinedTokenViolations.push(`${where}:${line}  ${text}（缺 --color-${token}）`);
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

if (undefinedTokenViolations.length > 0) {
  console.error(
    `[theme-colors] 发现 ${undefinedTokenViolations.length} 处使用了未声明主题颜色的工具类（Tailwind 不会生成对应样式）：`,
  );
  for (const violation of undefinedTokenViolations) {
    console.error(`  ${violation}`);
  }
  console.error(
    '\n处理方式：在 globals.css 的 @theme 里声明 --color-<name>，并在 :root 与 .dark 两套主题里定义对应变量（并核对对比度）；' +
      '或改用已有的语义色。',
  );
  process.exit(1);
}

console.log(`[theme-colors] 通过：扫描 ${scannedFiles} 个文件，无主题变量被包进颜色函数，语义色工具类均已声明。`);
