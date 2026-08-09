#!/usr/bin/env node
/**
 * next-intl mock 稳定性验证脚本（测试质量门禁，防 OOM 复发）。
 *
 * 背景：useTranslations() 若每次调用都返回一个新函数引用，依赖它的
 * useCallback/useEffect（dep 数组含 t）会在每次渲染时重建 → 组件无限重渲染 →
 * Vitest 堆溢出（FATAL ERROR: Ineffective mark-compacts near heap limit）。
 * 正确写法是把翻译函数提升为模块级稳定引用：
 *
 *   const stableT = (key: string) => key;
 *   vi.mock('next-intl', () => ({ useTranslations: () => stableT }));
 *
 * 本脚本扫描全部测试文件，硬拦截「不稳定 mock」两种形态：
 *   1. useTranslations: () => (key) => ...        （箭头简写直接返回箭头函数）
 *   2. useTranslations: () => { return (key) => ... }  （块体返回箭头函数）
 * 命中任一形态即退出码 1。挂在 pretest / lint 前，形成 CI 硬门禁。
 */

import { readdirSync, statSync, readFileSync } from 'node:fs';
import { resolve, join, dirname, relative } from 'node:path';
import { fileURLToPath } from 'node:url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);
const rootDir = resolve(__dirname, '..');
const srcDir = join(rootDir, 'src');

// 不稳定形态特征：useTranslations 返回「每次新建的函数」。
// 参数列表内允许嵌套括号（如 { count?: number }），故用 [^)]* 匹配到收尾的 ')'。
const UNSTABLE_MOCK_PATTERNS = [
  /useTranslations\s*:\s*\(\)\s*=>\s*\([^)]*\)\s*=>/g,
  /useTranslations\s*:\s*\(\)\s*=>\s*\{\s*return\s*\([^)]*\)\s*=>/g,
];

const TEST_FILE_RE = /\.(test|spec)\.(ts|tsx)$/;

function collectTestFiles(dirPath, out = []) {
  for (const entry of readdirSync(dirPath)) {
    const fullPath = join(dirPath, entry);
    const stat = statSync(fullPath);
    if (stat.isDirectory()) {
      collectTestFiles(fullPath, out);
    } else if (TEST_FILE_RE.test(entry)) {
      out.push(fullPath);
    }
  }
  return out;
}

function findViolations(source) {
  const violations = [];
  for (const pattern of UNSTABLE_MOCK_PATTERNS) {
    for (const match of source.matchAll(pattern)) {
      const line = source.slice(0, match.index).split('\n').length;
      violations.push(line);
    }
  }
  return [...new Set(violations)];
}

let hasErrors = false;
let scanned = 0;

console.log('🔍 验证 next-intl mock 稳定性（防 OOM 硬门禁）...');

for (const filePath of collectTestFiles(srcDir)) {
  scanned += 1;
  const source = readFileSync(filePath, 'utf-8');
  for (const line of findViolations(source)) {
    hasErrors = true;
    console.error(
      `  ❌ ${relative(rootDir, filePath)}:${line} 存在不稳定 next-intl mock（每次渲染新建函数 → 无限重渲染 → OOM）。`,
    );
    console.error(
      '     └ 请改为模块级稳定引用：const stableT = (key) => key; vi.mock(\'next-intl\', () => ({ useTranslations: () => stableT }));',
    );
  }
}

if (hasErrors) {
  console.error(`\n❌ 验证失败！请修复上述文件中的不稳定 mock 后重试。`);
  process.exit(1);
} else {
  console.log(`  ✅ 验证通过（扫描 ${scanned} 个测试文件，无不稳定 next-intl mock）。`);
  process.exit(0);
}
