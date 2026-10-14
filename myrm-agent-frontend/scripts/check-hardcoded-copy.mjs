#!/usr/bin/env node
/**
 * 硬编码文案门禁（棘轮）：`src/` 下 TSX 里绕过 i18n 的用户可见字面量，按文件计数，只降不升。
 *
 * 扫描规则见 `hardcoded-copy-scan.ts`，基线比较规则见 `hardcoded-copy-ratchet.ts`。存量很大且无法一次清零，
 * 所以用 `ci/hardcoded_copy_baseline.json` 冻结每个文件当前的数量：
 *   - 某文件数量高于基线（含基线里没有的新文件）→ 新增了硬编码文案，失败；
 *   - 某文件数量低于基线（含文件已删除或改名）→ 基线 drift，失败；不收紧的话，空出的额度会被后续改动悄悄占用。
 * 按文件而非总数计数，一个文件清掉的额度不能抵扣另一个文件的新增。
 *
 * 反向自检：扫描文件数为 0 时直接失败，而不是静默通过。
 *
 * 运行：bun scripts/check-hardcoded-copy.mjs
 *       bun scripts/check-hardcoded-copy.mjs --write-baseline  # 用当前值重写基线
 * 退出码：0 = 与基线一致；1 = 新增 / drift / 自检失败
 */

import { readFileSync, writeFileSync } from 'node:fs';
import { dirname, join, relative, resolve, sep } from 'node:path';
import { fileURLToPath } from 'node:url';

import { diffAgainstBaseline } from './hardcoded-copy-ratchet.ts';
import { findHardcodedCopySites } from './hardcoded-copy-scan.ts';
import { walkSourceFiles } from './source-files.mjs';

const rootDir = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const srcDir = join(rootDir, 'src');
const baselinePath = join(rootDir, 'scripts', 'ci', 'hardcoded_copy_baseline.json');
const SOURCE_EXTENSIONS = new Set(['.tsx']);
const MAX_LISTED_SITES = 8;

function fail(message) {
  console.error(`[hardcoded-copy] ${message}`);
  process.exit(1);
}

const startedAt = performance.now();
/** @type {Map<string, import('./hardcoded-copy-scan.ts').HardcodedCopySite[]>} */
const sitesByFile = new Map();
let scannedFiles = 0;
for (const file of walkSourceFiles(srcDir, SOURCE_EXTENSIONS)) {
  scannedFiles += 1;
  const sites = findHardcodedCopySites(readFileSync(file, 'utf8'), file);
  if (sites.length > 0) {
    sitesByFile.set(relative(rootDir, file).split(sep).join('/'), sites);
  }
}
if (scannedFiles === 0) {
  fail('自检失败：未扫描到任何源码文件，路径可能已失效——拒绝静默通过。');
}

const current = Object.fromEntries(
  [...sitesByFile].map(([file, sites]) => [file, sites.length]).sort(([a], [b]) => (a < b ? -1 : 1)),
);
const total = Object.values(current).reduce((sum, count) => sum + count, 0);

if (process.argv.includes('--write-baseline')) {
  writeFileSync(baselinePath, `${JSON.stringify(current, null, 2)}\n`, 'utf8');
  console.log(
    `[hardcoded-copy] 基线已写入 ${relative(rootDir, baselinePath)}：${Object.keys(current).length} 个文件、${total} 处。`,
  );
  process.exit(0);
}

let baseline;
try {
  baseline = JSON.parse(readFileSync(baselinePath, 'utf8'));
} catch (error) {
  fail(`无法读取基线 ${relative(rootDir, baselinePath)}: ${error.message}`);
}

const { increased, drifted } = diffAgainstBaseline(current, baseline);
const delta = (file) => `${baseline[file] ?? 0} → ${current[file] ?? 0}`;

if (increased.length > 0) {
  console.error('[hardcoded-copy] 新增硬编码文案（高于基线）：');
  for (const file of increased) {
    console.error(`    - ${file}: ${delta(file)}`);
    const sites = sitesByFile.get(file) ?? [];
    for (const { line, kind, text } of sites.slice(0, MAX_LISTED_SITES)) {
      console.error(`        :${line} [${kind}] ${text.length > 60 ? `${text.slice(0, 60)}…` : text}`);
    }
    if (sites.length > MAX_LISTED_SITES) {
      console.error(`        … 另有 ${sites.length - MAX_LISTED_SITES} 处`);
    }
  }
  console.error(
    '\n处理方式：文案写进 `locales/*.json` 并用 `useTranslations` 读取（中英双语）；品牌 / 单位 / 协议名这类不需要翻译的记号提取为具名常量。不要为了过门禁而重写基线。',
  );
}
if (drifted.length > 0) {
  console.error('[hardcoded-copy] 基线 drift（已改善但基线未收紧）：');
  for (const file of drifted) {
    console.error(`    - ${file}: ${delta(file)}`);
  }
  console.error('\n处理方式：运行 `bun scripts/check-hardcoded-copy.mjs --write-baseline` 收紧基线并一并提交。');
}
if (increased.length > 0 || drifted.length > 0) {
  process.exit(1);
}

const seconds = ((performance.now() - startedAt) / 1000).toFixed(1);
console.log(
  `[hardcoded-copy] OK：扫描 ${scannedFiles} 个 TSX 文件，存量 ${total} 处（${Object.keys(current).length} 个文件）与基线一致，用时 ${seconds}s。`,
);
