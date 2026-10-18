#!/usr/bin/env node
/**
 * 减少动态效果守卫门禁（零容忍 + 有理由的白名单）。
 *
 * 背景：`prefers-reduced-motion` 守卫是按文档生效的。Next 的主文档由 `src/app/globals.css` 覆盖，
 * 但 AI 生成的 widget、浏览器扩展 Side Panel、Tauri 自定义协议页各自是独立文档，宿主样式表不作用于
 * 它们。这类缺口在 jsdom 与普通单测里看不见（样式不参与断言），所以必须在静态阶段拦住。
 *
 * 判定规则见 `reduced-motion-scan.ts`：自拼 HTML 或样式表 + 带动画 + 没有 `prefers-reduced-motion`
 * 即失败；白名单只登记“确有理由不注入”的文件，理由必须与 `temp-docs/roadmap/topic_09` 记录一致。
 *
 * 反悔自检：扫描到的候选文件数为 0 时直接失败，而不是静默通过（路径失效必须暴露）。
 *
 * 运行：bun scripts/check-reduced-motion.mjs
 * 退出码：0 = 全部宿主自带守卫或已登记白名单；1 = 有遗漏 / 自检失败
 */

import { readdirSync, readFileSync } from 'node:fs';
import { dirname, join, relative, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import { scanReducedMotionSurfaces } from './reduced-motion-scan.ts';

const rootDir = resolve(dirname(fileURLToPath(import.meta.url)), '..');

/** 需要一起判定的包：前端自己，加上会产出独立文档的兄弟包。 */
const SCAN_ROOTS = ['src', '../myrm-agent-extension', '../myrm-agent-desktop', '../myrm-agent-server'];
/**
 * 剪掉依赖、构建产物、第三方快照与本地运行态：`.venv` 里是 patchright/playwright 自带的报告页，
 * `external_reference_project` 是竞品快照（含它们的测试页），`.myrm` 是 git 忽略的本地工作区数据
 * （基准夹具、临时产物），三者都不是我们的产品代码。
 */
const PRUNE_DIRS = new Set([
  'node_modules',
  '.next',
  'dist',
  'target',
  'build',
  '__pycache__',
  '.venv',
  'venv',
  '.mypy_cache',
  '.pytest_cache',
  'external_reference_project',
  '.myrm',
]);
const EXTENSIONS = new Set(['.ts', '.tsx', '.mjs', '.js', '.rs', '.py', '.html', '.css']);
const TEST_PATH = /(?:^|[\\/])__tests__[\\/]|\.test\.(?:tsx?|mjs|js)$/;

function* walk(dir) {
  let entries;
  try {
    entries = readdirSync(dir, { withFileTypes: true });
  } catch {
    return;
  }
  for (const entry of entries) {
    if (PRUNE_DIRS.has(entry.name)) {
      continue;
    }
    const full = join(dir, entry.name);
    if (entry.isDirectory()) {
      yield* walk(full);
      continue;
    }
    if (TEST_PATH.test(full)) {
      continue;
    }
    const dot = entry.name.lastIndexOf('.');
    if (dot !== -1 && EXTENSIONS.has(entry.name.slice(dot))) {
      yield full;
    }
  }
}

/** 相对**仓库根**（`myrm-agent/`）的路径，让白名单稳定、可读。 */
const repoRoot = resolve(rootDir, '..');

const files = [];
for (const scanRoot of SCAN_ROOTS) {
  for (const absolute of walk(resolve(rootDir, scanRoot))) {
    files.push({ path: relative(repoRoot, absolute), source: readFileSync(absolute, 'utf8') });
  }
}

const { violations, allowlisted, scanned } = scanReducedMotionSurfaces(files);

if (scanned === 0) {
  console.error('[reduced-motion] 自检失败：未扫描到任何候选文件，扫描路径可能已失效——拒绝静默通过。');
  process.exit(1);
}

if (violations.length > 0) {
  console.error(`[reduced-motion] 发现 ${violations.length} 个独立文档宿主带动画却没有 prefers-reduced-motion 守卫：`);
  for (const { path, evidence } of violations) {
    console.error(`  ${path}  （动画：${evidence}）`);
  }
  console.error(
    '\n处理方式：在该文档自己的样式里追加 `@media (prefers-reduced-motion: reduce)` 守卫；' +
      '若确认不需要（例如动画不是循环、或动画本身就是交付物），在 scripts/reduced-motion-scan.ts 的' +
      ' `ALLOWED_WITHOUT_GUARD` 里登记并写明理由，同时同步 temp-docs/roadmap/topic_09。',
  );
  process.exit(1);
}

const allowlistedNote =
  allowlisted.length === 0
    ? ''
    : `；白名单 ${allowlisted.length} 个（${allowlisted.map((item) => item.path).join('、')}）`;
console.log(`[reduced-motion] 通过：扫描 ${scanned} 个文件，独立文档宿主均自带守卫${allowlistedNote}。`);
