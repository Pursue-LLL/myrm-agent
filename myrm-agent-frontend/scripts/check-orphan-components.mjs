#!/usr/bin/env node
/**
 * 孤儿模块门禁：拦截「只有自己的测试引用、生产代码无人引用」的组件。
 *
 * 背景：单元测试通过相对/别名路径 import 被测文件，因此一个组件即使从产品
 * 入口不可达，它的测试依然全绿——测试绿不等于代码活着。实测曾出现
 * `FactCheckSheetViewer.tsx`（385 行）在父组件被删除后长期存活，套件全绿掩盖
 * 了这一事实。本门禁补上这个结构性盲区。
 *
 * 判定口径（避免误报，三条同时成立才算孤儿）：
 *   1. 文件位于 `src/components/`（组件目录；`src/app/` 路由页天然不被 import）
 *   2. 解析真实模块说明符（`import ... from '...'` / `export ... from '...'` /
 *      动态 `import('...')`），而非按文件名子串匹配——子串会命中同名标识符造成
 *      大量误报（实测 667 个假阳性）
 *   3. 排除测试文件自身的引用；且没有任何生产文件 import 它
 *
 * 反向自检：若待扫描组件数为 0，说明路径或解析器失效，直接失败而非静默通过。
 *
 * 基线：`scripts/ci/orphan_components_baseline.txt` 登记存量孤儿（本门禁上线前已存在，
 * 归属各自模块后续处理）。门禁只拦截**新增**孤儿，使存量债不阻塞 CI 又让趋势只降不升；
 * 基线中已不再孤儿的条目会被报为 drift（应删除以收紧基线）。
 *
 * 豁免：在组件文件顶部（前 30 行内）加 `@orphan-ok <理由>` 即为有意保留
 * （例如仅被测试或外部动态引用），需写明理由以便复核。
 *
 * 运行：bun scripts/check-orphan-components.mjs
 *       bun scripts/check-orphan-components.mjs --ratchet  # 用当前孤儿重写基线
 * 退出码：0 = 无新增孤儿且基线无 drift；1 = 发现新增孤儿 / drift / 自检失败
 */

import { readdirSync, statSync, readFileSync, writeFileSync } from 'node:fs';
import { resolve, join, dirname, relative, extname } from 'node:path';
import { fileURLToPath } from 'node:url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);
const rootDir = resolve(__dirname, '..');
const srcDir = join(rootDir, 'src');
const componentsDir = join(srcDir, 'components');
const baselinePath = join(__dirname, 'ci', 'orphan_components_baseline.txt');

const SOURCE_EXTENSIONS = new Set(['.ts', '.tsx']);
const PRUNE_DIRS = new Set(['node_modules', '.next', 'dist', '__tests__', '__mocks__']);
const EXEMPT_MARKER = '@orphan-ok';
const EXEMPT_SCAN_LINES = 30;

// Only real components are in scope: app-route pages are entry points, and
// non-component .ts/.tsx modules (hooks, utils, barrels) are not mountable units.
const NON_COMPONENT_BASENAMES = new Set(['index', 'layout', 'page', 'loading', 'error', 'not-found', 'route']);

const isTestFile = (path) => /\.(test|spec)\./.test(path) || path.includes('__tests__');

function isScannableComponent(file) {
  const basename = file.slice(file.lastIndexOf('/') + 1).replace(/\.tsx?$/, '');
  if (NON_COMPONENT_BASENAMES.has(basename)) {
    return false;
  }
  // PascalCase (or camelCase with a capital) signals a component; lowercase-only names are
  // helpers/hooks/theme scripts.
  return /[A-Z]/.test(basename.slice(0, 1));
}

function walk(dir, out = [], predicate = () => true) {
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    if (PRUNE_DIRS.has(entry.name)) {
      continue;
    }
    const full = join(dir, entry.name);
    if (entry.isDirectory()) {
      walk(full, out, predicate);
    } else if (SOURCE_EXTENSIONS.has(extname(entry.name)) && predicate(full)) {
      out.push(full);
    }
  }
  return out;
}

/** Resolve a module specifier to a real source file, mirroring tsconfig path aliases. */
function resolveSpecifier(specifier, fromFile) {  let base;
  if (specifier.startsWith('@/')) {
    base = join(srcDir, specifier.slice(2));
  } else if (specifier.startsWith('.')) {
    base = resolve(dirname(fromFile), specifier);
  } else {
    return null;
  }
  const candidates = [
    base,
    `${base}.ts`,
    `${base}.tsx`,
    join(base, 'index.ts'),
    join(base, 'index.tsx'),
  ];
  for (const candidate of candidates) {
    try {
      if (statSync(candidate).isFile()) {
        return candidate;
      }
    } catch {
      // keep probing
    }
  }
  return null;
}

const IMPORT_PATTERNS = [
  /(?:import|export)[^;'"`]*?from\s*['"]([^'"]+)['"]/gs,
  /import\s*\(\s*['"]([^'"]+)['"]\s*\)/g,
];

function collectImportedFiles(allFiles) {
  const imported = new Set();
  for (const file of allFiles) {
    if (isTestFile(file)) {
      continue;
    }
    const content = readFileSync(file, 'utf8');
    for (const pattern of IMPORT_PATTERNS) {
      for (const match of content.matchAll(pattern)) {
        const target = resolveSpecifier(match[1], file);
        if (target) {
          imported.add(target);
        }
      }
    }
  }
  return imported;
}
function readExemption(file) {
  const head = readFileSync(file, 'utf8').split('\n', EXEMPT_SCAN_LINES).join('\n');
  const markerIndex = head.indexOf(EXEMPT_MARKER);
  return markerIndex === -1 ? null : head.slice(markerIndex).split('\n')[0].trim();
}

let componentFiles;
try {
  componentFiles = walk(componentsDir, [], (file) => !isTestFile(file) && isScannableComponent(file));
} catch (error) {
  console.error(`[orphan-gate] 无法扫描 ${relative(rootDir, componentsDir)}: ${error.message}`);
  process.exit(1);
}

if (componentFiles.length === 0) {
  console.error(
    `[orphan-gate] 自检失败：未在 ${relative(rootDir, componentsDir)} 扫描到任何组件文件，` +
      '路径或扩展名配置可能已失效——拒绝静默通过。',
  );
  process.exit(1);
}

const importedByProduction = collectImportedFiles(walk(srcDir));
const orphans = [];

for (const file of componentFiles) {
  if (importedByProduction.has(file)) {
    continue;
  }
  const exemption = readExemption(file);
  if (exemption) {
    console.log(`[orphan-gate] 豁免 ${relative(rootDir, file)} :: ${exemption}`);
    continue;
  }
  orphans.push(relative(rootDir, file));
}

orphans.sort();

if (process.argv.includes('--ratchet')) {
  const header =
    '# 存量孤儿组件基线（scripts/check-orphan-components.mjs）\n' +
    '# 每行一个相对 myrm-agent-frontend 的路径；仅登记本门禁上线前已存在的孤儿。\n' +
    '# 新增孤儿会被门禁拦截；条目不再孤儿时会被报为 drift，需从基线删除。\n';
  writeFileSync(baselinePath, header + orphans.map((o) => `${o}\n`).join(''), 'utf8');
  console.log(`[orphan-gate] 基线已写入 ${relative(rootDir, baselinePath)}（${orphans.length} 条）`);
  process.exit(0);
}

let baselined = new Set();
try {
  baselined = new Set(
    readFileSync(baselinePath, 'utf8')
      .split('\n')
      .map((line) => line.trim())
      .filter((line) => line && !line.startsWith('#')),
  );
} catch (error) {
  console.error(`[orphan-gate] 无法读取基线 ${relative(rootDir, baselinePath)}: ${error.message}`);
  process.exit(1);
}

const newOrphans = orphans.filter((orphan) => !baselined.has(orphan));
const drifted = [...baselined].filter((entry) => !orphans.includes(entry));

if (newOrphans.length > 0) {
  console.error(`[orphan-gate] 新增 ${newOrphans.length} 个孤儿组件（无任何生产代码引用）：`);
  for (const orphan of newOrphans) {
    console.error(`    - ${orphan}`);
  }
  console.error(
    '\n处理方式：接入产品入口；或在文件顶部注释加 ' +
      `\`${EXEMPT_MARKER} <理由>\` 说明为何有意保留（须可复核）。`,
  );
}

if (drifted.length > 0) {
  console.error(`[orphan-gate] 基线 drift：${drifted.length} 条已不再是孤儿，请从基线移除（收紧口径）：`);
  for (const entry of drifted) {
    console.error(`    - ${entry}`);
  }
}

if (newOrphans.length > 0 || drifted.length > 0) {
  process.exit(1);
}

console.log(
  `[orphan-gate] OK：${componentFiles.length} 个组件均有生产引用或已豁免；` +
    `存量基线 ${baselined.size} 条，无新增、无 drift。`,
);
