#!/usr/bin/env node
/**
 * 无障碍门禁：jsx-a11y 的各规则告警数与规则豁免总数只降不升（棘轮），
 * 且不允许出现“写了 outline-none 却没有可见焦点替代”的元素（硬门禁，零容忍）。
 *
 * 背景：jsx-a11y 规则全部为 `warn`，`bun run lint` 不会因告警失败，新增的 `role="button"` /
 * 无键盘支持的点击元素会悄无声息地把已清理的存量再推回去；而单纯用 `oxlint-disable` 豁免也能让
 * 告警数“变好”却没有改善真实可用性。本门禁同时约束两个口径：
 *   1. 每条 jsx-a11y 规则的告警数（来自 oxlint JSON 输出）
 *   2. `oxlint-disable* ... jsx-a11y/*` 豁免注释总数（防止用豁免刷指标）
 *
 * 基线 `scripts/ci/a11y_ratchet_baseline.json` 登记当前存量。当前值高于基线 → 新增退化，失败；
 * 低于基线 → 基线 drift，失败（需用 `--ratchet` 收紧，否则空出的额度会被后续改动悄悄占用）。
 *
 * 硬门禁（键盘焦点可见性）：全局 focus-ring.css 在 `@layer base`，会被 `outline-none` 覆盖，而 jsx-a11y/axe
 * 都无法判断聚焦后是否可见。`focus-visibility-scan.ts` 解析 className 属性值，凡含 `outline-none/hidden/0`
 * 且无生效的 `focus(-visible)?:ring/border/shadow/bg/...` 替代（`ring-0` 等无效写法不算）的元素一律失败；
 * 共享 `Input` 原语自带焦点环，其上写 `focus(-visible):ring-0` 且无替代同样失败。
 * 原生文本输入与 `*Input/*Select/*Textarea` 封装、媒体、Radix 浮层 `*.Content` 容器与 `tabIndex={-1}` 元素自动豁免。
 *
 * 反向自检：oxlint 未产出可解析 JSON 或扫描文件数为 0 时直接失败，而不是静默通过。
 *
 * 运行：bun scripts/check-a11y-ratchet.mjs
 *       bun scripts/check-a11y-ratchet.mjs --ratchet  # 用当前值重写基线
 * 退出码：0 = 与基线一致；1 = 退化 / drift / 自检失败
 */

import { spawnSync } from 'node:child_process';
import { readFileSync, readdirSync, writeFileSync } from 'node:fs';
import { dirname, extname, join, relative, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import { findInvisibleFocusSites } from './focus-visibility-scan.ts';

const rootDir = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const srcDir = join(rootDir, 'src');
const baselinePath = join(rootDir, 'scripts', 'ci', 'a11y_ratchet_baseline.json');

const OXLINT_BIN = join(rootDir, 'node_modules', 'oxlint', 'bin', 'oxlint');
const A11Y_CODE = /^jsx-a11y\(([^)]+)\)$/;
const WAIVER_PATTERN = /oxlint-disable(?:-next-line|-line)?[^\n]*jsx-a11y\//g;
const SOURCE_EXTENSIONS = new Set(['.ts', '.tsx']);
const PRUNE_DIRS = new Set(['node_modules', '.next', 'dist']);
const TEST_PATH = /(?:^|[\\/])__tests__[\\/]|\.test\.tsx?$/;

function fail(message) {
  console.error(`[a11y-ratchet] ${message}`);
  process.exit(1);
}

function countRuleWarnings() {
  const run = spawnSync(process.execPath, [OXLINT_BIN, '--ignore-path', '.oxlintignore', '--format', 'json'], {
    cwd: rootDir,
    encoding: 'utf8',
    maxBuffer: 256 * 1024 * 1024,
  });
  let report;
  try {
    report = JSON.parse(run.stdout);
  } catch {
    fail(`oxlint 未输出可解析的 JSON（exit ${run.status}）：${(run.stderr || run.stdout).slice(0, 300)}`);
  }
  if (!report.number_of_files) {
    fail('自检失败：oxlint 未扫描到任何文件，配置或路径可能已失效——拒绝静默通过。');
  }
  const counts = {};
  for (const { code } of report.diagnostics) {
    const rule = A11Y_CODE.exec(code)?.[1];
    if (rule) {
      counts[rule] = (counts[rule] ?? 0) + 1;
    }
  }
  return counts;
}

function countWaivers(dir) {
  let total = 0;
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    if (PRUNE_DIRS.has(entry.name)) {
      continue;
    }
    const full = join(dir, entry.name);
    if (entry.isDirectory()) {
      total += countWaivers(full);
    } else if (SOURCE_EXTENSIONS.has(extname(entry.name))) {
      total += readFileSync(full, 'utf8').match(WAIVER_PATTERN)?.length ?? 0;
    }
  }
  return total;
}

function collectInvisibleFocusSites(dir) {
  const found = [];
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    if (PRUNE_DIRS.has(entry.name)) {
      continue;
    }
    const full = join(dir, entry.name);
    if (entry.isDirectory()) {
      found.push(...collectInvisibleFocusSites(full));
    } else if (extname(entry.name) === '.tsx' && !TEST_PATH.test(full)) {
      for (const { line, tag } of findInvisibleFocusSites(readFileSync(full, 'utf8'))) {
        found.push(`${relative(rootDir, full)}:${line} <${tag}>`);
      }
    }
  }
  return found;
}

const invisibleFocusSites = collectInvisibleFocusSites(srcDir);
if (invisibleFocusSites.length > 0) {
  console.error('[a11y-ratchet] 键盘焦点不可见（outline-none 无 focus-visible 替代）：');
  invisibleFocusSites.forEach((site) => console.error(`    - ${site}`));
  console.error(
    '\n处理方式：补 `focus-visible:ring-2 focus-visible:ring-ring`（被容器内边距包裹的元素加 `focus-visible:ring-inset`）；若元素仅被程序化聚焦，改用 `tabIndex={-1}`。',
  );
  process.exit(1);
}

const current = { rules: countRuleWarnings(), waivers: countWaivers(srcDir) };

if (process.argv.includes('--ratchet')) {
  const sortedRules = Object.fromEntries(Object.entries(current.rules).sort(([a], [b]) => a.localeCompare(b)));
  writeFileSync(baselinePath, `${JSON.stringify({ rules: sortedRules, waivers: current.waivers }, null, 2)}\n`, 'utf8');
  console.log(`[a11y-ratchet] 基线已写入 ${relative(rootDir, baselinePath)}`);
  process.exit(0);
}

let baseline;
try {
  baseline = JSON.parse(readFileSync(baselinePath, 'utf8'));
} catch (error) {
  fail(`无法读取基线 ${relative(rootDir, baselinePath)}: ${error.message}`);
}

const metrics = [...new Set([...Object.keys(baseline.rules), ...Object.keys(current.rules)])].map((rule) => ({
  name: `jsx-a11y/${rule}`,
  now: current.rules[rule] ?? 0,
  base: baseline.rules[rule] ?? 0,
}));
metrics.push({ name: '豁免注释（oxlint-disable ... jsx-a11y/）', now: current.waivers, base: baseline.waivers });

const regressed = metrics.filter((m) => m.now > m.base);
const drifted = metrics.filter((m) => m.now < m.base);
const format = (m) => `    - ${m.name}: ${m.base} → ${m.now}`;

if (regressed.length > 0) {
  console.error('[a11y-ratchet] 无障碍退化（高于基线）：');
  regressed.forEach((m) => console.error(format(m)));
  console.error(
    '\n处理方式：改用原生元素（button/a）或补齐键盘支持（见 src/lib/utils/a11y.ts 的 activateOnKey）；不要新增豁免刷指标。',
  );
}
if (drifted.length > 0) {
  console.error('[a11y-ratchet] 基线 drift（已改善但基线未收紧）：');
  drifted.forEach((m) => console.error(format(m)));
  console.error('\n处理方式：运行 `bun scripts/check-a11y-ratchet.mjs --ratchet` 收紧基线并一并提交。');
}
if (regressed.length > 0 || drifted.length > 0) {
  process.exit(1);
}

const total = Object.values(current.rules).reduce((sum, n) => sum + n, 0);
console.log(
  `[a11y-ratchet] OK：jsx-a11y 告警 ${total} 条、豁免 ${current.waivers} 条，与基线一致；键盘焦点可见性 0 违规。`,
);
