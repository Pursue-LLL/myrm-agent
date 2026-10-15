#!/usr/bin/env node
/**
 * 硬编码文案门禁：`src/` 下绕过 i18n 的用户可见字面量，分两类把关。
 *
 * 1. TSX 的 JSX 字面量（棘轮）：按文件计数，只降不升。扫描规则见 `hardcoded-copy-scan.ts`，基线比较规则见
 *    `hardcoded-copy-ratchet.ts`。存量很大且无法一次清零，所以用 `ci/hardcoded_copy_baseline.json` 冻结每个文件当前的数量：
 *    - 某文件数量高于基线（含基线里没有的新文件）→ 新增了硬编码文案，失败；
 *    - 某文件数量低于基线（含文件已删除或改名）→ 基线 drift，失败；不收紧的话，空出的额度会被后续改动悄悄占用。
 *    按文件而非总数计数，一个文件清掉的额度不能抵扣另一个文件的新增。
 *    基线只能收紧：`--write-baseline` 写入 `min(当前, 基线)`（见 `ratchet-baseline.ts`），不会新增文件条目、
 *    也不会抬高已有条目，所以它不能被用来把新增的硬编码文案“洗”进基线。
 *
 * 2. toast 文案（零容忍）：`.ts` / `.tsx` 里 toast 调用写死的文案，规则见 `toast-copy-scan.ts`。存量已清零，没有基线，
 *    出现一处即失败——toast 弹在事件处理里，类型检查与单测都看不到，其余语言的用户只会直接看到原文。
 *
 * 反向自检：扫描文件数为 0 时直接失败，而不是静默通过。
 *
 * 运行：bun scripts/check-hardcoded-copy.mjs
 *       bun scripts/check-hardcoded-copy.mjs --write-baseline  # 只把降低的 JSX 额度写进基线
 * 退出码：0 = 通过；1 = JSX 新增 / drift、出现 toast 硬编码文案或自检失败
 */
import { readFileSync, writeFileSync } from 'node:fs';
import { dirname, join, relative, resolve, sep } from 'node:path';
import { fileURLToPath } from 'node:url';

import { diffAgainstBaseline } from './hardcoded-copy-ratchet.ts';
import { findHardcodedCopySites } from './hardcoded-copy-scan.ts';
import { tightenCounts } from './ratchet-baseline.ts';
import { walkSourceFiles } from './source-files.mjs';
import { findToastCopySites } from './toast-copy-scan.ts';

const rootDir = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const srcDir = join(rootDir, 'src');
const baselinePath = join(rootDir, 'scripts', 'ci', 'hardcoded_copy_baseline.json');
const SOURCE_EXTENSIONS = new Set(['.ts', '.tsx']);
const MAX_LISTED_SITES = 8;

function fail(message) {
  console.error(`[hardcoded-copy] ${message}`);
  process.exit(1);
}

const truncate = (text) => (text.length > 60 ? `${text.slice(0, 60)}…` : text);

const startedAt = performance.now();
/** @type {Map<string, import('./hardcoded-copy-scan.ts').HardcodedCopySite[]>} */
const sitesByFile = new Map();
/** @type {Map<string, import('./toast-copy-scan.ts').ToastCopySite[]>} */
const toastSitesByFile = new Map();
let scannedFiles = 0;
let scannedTsxFiles = 0;
for (const file of walkSourceFiles(srcDir, SOURCE_EXTENSIONS)) {
  if (file.endsWith('.d.ts')) {
    continue;
  }
  scannedFiles += 1;
  const source = readFileSync(file, 'utf8');
  const relativePath = relative(rootDir, file).split(sep).join('/');

  if (file.endsWith('.tsx')) {
    scannedTsxFiles += 1;
    const sites = findHardcodedCopySites(source, file);
    if (sites.length > 0) {
      sitesByFile.set(relativePath, sites);
    }
  }
  const toastSites = findToastCopySites(source, file);
  if (toastSites.length > 0) {
    toastSitesByFile.set(relativePath, toastSites);
  }
}
if (scannedFiles === 0) {
  fail('自检失败：未扫描到任何源码文件，路径可能已失效——拒绝静默通过。');
}

const current = Object.fromEntries(
  [...sitesByFile].map(([file, sites]) => [file, sites.length]).sort(([a], [b]) => (a < b ? -1 : 1)),
);
const total = Object.values(current).reduce((sum, count) => sum + count, 0);

let baseline;
try {
  baseline = JSON.parse(readFileSync(baselinePath, 'utf8'));
} catch (error) {
  fail(`无法读取基线 ${relative(rootDir, baselinePath)}: ${error.message}`);
}

if (process.argv.includes('--write-baseline')) {
  const tightened = tightenCounts(current, baseline);
  const tightenedFiles = Object.keys(baseline).filter((file) => tightened[file] !== baseline[file]).length;
  if (tightenedFiles > 0) {
    writeFileSync(baselinePath, `${JSON.stringify(tightened, null, 2)}\n`, 'utf8');
  }
  console.log(`[hardcoded-copy] 基线已收紧 ${tightenedFiles} 个文件（${relative(rootDir, baselinePath)}）。`);
  // 新增的额度不会被写入：继续按收紧后的基线比较，仍高于基线时如实失败。
  baseline = tightened;
}

const { increased, drifted } = diffAgainstBaseline(current, baseline);
const delta = (file) => `${baseline[file] ?? 0} → ${current[file] ?? 0}`;

if (increased.length > 0) {
  console.error('[hardcoded-copy] 新增硬编码文案（高于基线）：');
  for (const file of increased) {
    console.error(`    - ${file}: ${delta(file)}`);
    const sites = sitesByFile.get(file) ?? [];
    for (const { line, kind, text } of sites.slice(0, MAX_LISTED_SITES)) {
      console.error(`        :${line} [${kind}] ${truncate(text)}`);
    }
    if (sites.length > MAX_LISTED_SITES) {
      console.error(`        … 另有 ${sites.length - MAX_LISTED_SITES} 处`);
    }
  }
  console.error(
    '\n处理方式：文案写进 `locales/*.json` 并用 `useTranslations` 读取（中英双语）；品牌 / 单位 / 协议名这类不需要翻译的记号提取为具名常量。基线只降不升，`--write-baseline` 不会把新增写进去。',
  );
}
if (drifted.length > 0) {
  console.error('[hardcoded-copy] 基线 drift（已改善但基线未收紧）：');
  for (const file of drifted) {
    console.error(`    - ${file}: ${delta(file)}`);
  }
  console.error(
    '\n处理方式：运行 `bun scripts/check-hardcoded-copy.mjs --write-baseline` 收紧基线（只写入降低的额度）并一并提交。',
  );
}
if (toastSitesByFile.size > 0) {
  console.error('[hardcoded-copy] toast 里写死了用户可见文案（零容忍，没有基线）：');
  for (const [file, sites] of toastSitesByFile) {
    console.error(`    - ${file}: ${sites.length} 处`);
    for (const { line, text } of sites.slice(0, MAX_LISTED_SITES)) {
      console.error(`        :${line} ${truncate(text)}`);
    }
    if (sites.length > MAX_LISTED_SITES) {
      console.error(`        … 另有 ${sites.length - MAX_LISTED_SITES} 处`);
    }
  }
  console.error(
    "\n处理方式：组件内用 `useTranslations` 取文案；store / 工具函数用 `@/services/i18nToastService` 的 `showI18nToast` / `translateI18nKey`。`t(key) || 'x'` 的兜底永远不会执行（缺键时 `t` 返回键路径），直接删掉。",
  );
}
if (increased.length > 0 || drifted.length > 0 || toastSitesByFile.size > 0) {
  process.exit(1);
}

const seconds = ((performance.now() - startedAt) / 1000).toFixed(1);
console.log(
  `[hardcoded-copy] OK：扫描 ${scannedTsxFiles} 个 TSX 文件，存量 ${total} 处（${Object.keys(current).length} 个文件）与基线一致；${scannedFiles} 个源码文件的 toast 文案全部走 i18n，用时 ${seconds}s。`,
);
