#!/usr/bin/env node
/**
 * ICU 语法门禁：`locales/*.json` 里每条文案都必须是 next-intl 能解析的 ICU 消息，零容忍。
 *
 * 扫描规则见 `icu-syntax-scan.ts`。无效文案（`{{count}}`、裸 `<token>`、裸 JSON 花括号）在运行时的表现随构建而变：
 * 开发构建抛 `INVALID_MESSAGE`，生产构建带插值参数时同样失败并把键路径显示给用户，不带参数时又碰巧原样显示，
 * 所以只能在源头拦截，不能依赖运行时表现。
 *
 * 反向自检：没有 locale 文件或解析的文案数为 0 时直接失败，而不是静默通过。
 *
 * 运行：bun scripts/check-icu-syntax.mjs
 * 退出码：0 = 全部有效；1 = 存在无效文案 / 自检失败
 */

import { readdirSync, readFileSync } from 'node:fs';
import { basename, dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import { scanIcuMessages, scanTranslationArtifacts } from './icu-syntax-scan.ts';

const rootDir = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const localesDir = join(rootDir, 'locales');
const MAX_LISTED_PER_LOCALE = 20;

function fail(message) {
  console.error(`[icu-syntax] ${message}`);
  process.exit(1);
}

const startedAt = performance.now();
const localeFiles = readdirSync(localesDir)
  .filter((name) => name.endsWith('.json'))
  .sort();
if (localeFiles.length === 0) {
  fail('自检失败：未找到任何 locale 文件，路径可能已失效——拒绝静默通过。');
}

let scanned = 0;
let invalidTotal = 0;
let artifactTotal = 0;
for (const file of localeFiles) {
  const locale = basename(file, '.json');
  const tree = JSON.parse(readFileSync(join(localesDir, file), 'utf8'));
  const result = scanIcuMessages(tree);
  scanned += result.scanned;
  const artifacts = scanTranslationArtifacts(tree);
  artifactTotal += artifacts.invalid.length;
  if (artifacts.invalid.length > 0) {
    console.error(`[icu-syntax] ${locale}: ${artifacts.invalid.length} 条文案残留机翻保护标记：`);
    for (const { path, error } of artifacts.invalid.slice(0, MAX_LISTED_PER_LOCALE)) {
      console.error(`    - ${path}: ${error}`);
    }
  }
  if (result.invalid.length === 0) {
    continue;
  }
  invalidTotal += result.invalid.length;
  console.error(`[icu-syntax] ${locale}: ${result.invalid.length} 条无效 ICU 文案：`);
  for (const { path, error } of result.invalid.slice(0, MAX_LISTED_PER_LOCALE)) {
    console.error(`    - ${path}: ${error}`);
  }
  if (result.invalid.length > MAX_LISTED_PER_LOCALE) {
    console.error(`    … 另有 ${result.invalid.length - MAX_LISTED_PER_LOCALE} 条`);
  }
}
if (scanned === 0) {
  fail('自检失败：未解析到任何文案，locale 文件结构可能已变——拒绝静默通过。');
}
if (artifactTotal > 0) {
  console.error(
    '\n处理方式：这些 `__BR_…__` / `__PHn__` 是机翻时的品牌 / 占位符保护记号，还原环节漏掉了。' +
      '把对应文案改回正常写法；若来自 `scripts/i18n-de-bulk-translate.py`，检查品牌保护的还原结果。',
  );
  process.exit(1);
}
if (invalidTotal > 0) {
  console.error(
    '\n处理方式：插值变量写成 `{name}`；要原样显示的花括号 / 尖括号，把以它开头的片段用单引号括起来，' +
      "如 `'{{secret:KEY}}'`、`'<token>'`、`[ '{\"a\": 1}' ]`（单引号必须紧贴 `{` `}` `<` `>`，否则不构成转义）。",
  );
  process.exit(1);
}

const seconds = ((performance.now() - startedAt) / 1000).toFixed(2);
console.log(`[icu-syntax] OK：${localeFiles.length} 个 locale 共 ${scanned} 条文案全部是有效 ICU，用时 ${seconds}s。`);
