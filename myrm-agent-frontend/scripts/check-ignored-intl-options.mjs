#!/usr/bin/env node
/**
 * next-intl 忽略选项门禁（零容忍）：翻译调用里不得再出现 `defaultValue` / `defaultMessage`。
 *
 * 背景：next-intl 不读这两个选项，缺键时返回键路径。它们在仓库里出现过两百多处，兜底串从不显示，
 * 却掩盖过「读错命名空间」「键没加进语言包」这类真实错误；静态门禁只认字面量键，抓不到。
 * 判定规则见 `ignored-intl-options-scan.ts`；开放词表的兜底改用 `lib/i18n/translateOrRaw`。
 *
 * 反向自检：扫描到的源文件数为 0 时直接失败，而不是静默通过（路径失效必须暴露）。
 *
 * 运行：bun scripts/check-ignored-intl-options.mjs
 * 退出码：0 = 没有被忽略的选项；1 = 存在 / 自检失败
 */

import { readFileSync } from 'node:fs';
import { dirname, relative, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import { findIgnoredIntlOptions } from './ignored-intl-options-scan.ts';
import { walkSourceFiles } from './source-files.mjs';

const rootDir = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const srcDir = resolve(rootDir, 'src');
/** 先用文本过滤掉绝大多数文件，只对命中的文件做语法树解析。 */
const OPTION_TEXT = /default(?:Value|Message)/;

let scanned = 0;
const offenders = [];
for (const file of walkSourceFiles(srcDir, new Set(['.ts', '.tsx']))) {
  scanned += 1;
  const source = readFileSync(file, 'utf-8');
  if (!OPTION_TEXT.test(source)) {
    continue;
  }
  for (const hit of findIgnoredIntlOptions(source, file)) {
    offenders.push(`  ${relative(rootDir, file)}:${hit.line}  ${hit.callee}(…, { ${hit.option} })`);
  }
}

if (scanned === 0) {
  console.error('[intl-options] 自检失败：未找到任何源文件，路径可能已失效——拒绝静默通过。');
  process.exit(1);
}
if (offenders.length > 0) {
  console.error(`[intl-options] ${offenders.length} 处翻译调用带着 next-intl 不读取的选项：`);
  console.error(offenders.join('\n'));
  console.error('\n闭集键直接 t(key)；服务端开放词表用 lib/i18n/translateOrRaw（语言包有键就翻译，没有就原样显示）。');
  process.exit(1);
}
console.log(
  `[intl-options] OK：扫描 ${scanned} 个源文件，没有被 next-intl 忽略的 defaultValue / defaultMessage 选项。`,
);
