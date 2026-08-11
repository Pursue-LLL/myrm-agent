#!/usr/bin/env node
/**
 * 代码引用 → en.json 键存在性门禁（i18n 门禁 9l）。
 *
 * 补上 verify-i18n.mjs 的测量盲区：前者只校验 locale 文件间的 parity / 纯净性，
 * 无法发现「组件 t() 引用但 en.json（SSOT）根本不存在」的键。后者运行时
 * 无 getMessageFallback（见 src/i18n/request.ts），缺失键直接显示原始 key
 * （MISSING_MESSAGE），对用户是明显产品缺陷。
 *
 * 本门禁静态扫描 src/**\/*.{ts,tsx}，提取三类翻译引用并逐一 resolve 到 en.json：
 * - useTranslations('ns') 绑定后的 t('key') → 完整键 ns.key
 * - useTranslations()（根）绑定后的 t('key') → 完整键 key
 * - getTranslations({ locale, namespace: 'ns' }) 绑定后的 t('key') → ns.key
 * - showI18nToast('key', ...) 的 titleKey / options 中 descriptionKey / action.label → 完整键 key（不经命名空间归因）；三元 descriptionKey / action.label（`cond ? 'a' : 'b'`）两个分支也纳入校验
 *
 * 归因策略：以「最近前驱同名绑定」关联调用与命名空间——组件内 `const t = ...`
 * 的遮蔽天然形成作用域边界，无需完整 JS 解析器；调用位于同名绑定声明之前（helper
 * 函数前置定义、t 由组件体传入）时，退化为「文件内同名绑定命名空间并集」验证（任一
 * 候选命名空间存在该键即通过，避免误报）；动态 key（模板串/变量）无法静态 resolve，
 * 跳过（运行时仍会显示 key 本身，但不属于本门禁可静态判定的范围）。
 *
 * 无绑定文件的盲区治理：props 传入 t（如 `useAgentEditor(id, isNew, t)`、helper 接收
 * `t` 参数）的文件自身没有 useTranslations 绑定，直接跳过会漏检「根命名空间引用但键
 * 缺失」类缺陷（如根 t('error') 而根无 error 键）。本门禁的「调用方递归继承」策略：
 * - 真实 import 解析：解析各文件的 import/export-from 语句（相对路径、@/ 别名），
 *   构建「被导入文件 → 引用方文件」映射，避免同名 basename 匹配造成的串链误归因
 *   （如 MemoryCommandCenterPanels 与同目录其他文件）。
 * - 调用点实参推导：调用方若把翻译绑定作为函数实参或 JSX 属性值传入当前模块
 *   （`resolveScopeNote(..., tHumanize)`、`<Comp t={t} />`），说明被调用模块的翻译
 *   函数参数来源确定，直接采用该绑定的命名空间，比按同名 `t` 归因更精确（scopeNote
 *   的 t 实参是 tHumanize→humanize，而非 toolApproval）。
 * - 递归兜底：前述两层都失效时沿 import 链向上 BFS（seen 防环、无固定深度上限，
 *   兼容多级 helper 转发链），直到找到同名 `t` 绑定的调用方。
 * - 任一候选命名空间（含根 ''）存在该键即通过；BFS 无法解析（链断裂）时跳过该文件，
 *   避免误报。
 *
 * 动态命名空间排除：`useTranslations(<变量>)`（如 SchemaForm 的 translationNamespace
 * prop、ThemePackageImportPreview 的 translationNamespace prop）的运行时命名空间由
 * 调用方/调用点决定，无法静态归因，与动态 key 同理直接跳过——既不能递归继承（会误归因
 * 到调用方其他翻译绑定，如 settings.retrieval），也不能断言缺失。
 *
 * 排除项：
 * - __tests__ / *.test.* / *.spec.*：测试文件用 mock translator，不产生真实 UI 引用
 * - .next / node_modules / public / scripts：非运行时源码
 * - useTranslations(dynamicVar) / getTranslations({ namespace: dynamicVar })：无法静态归因
 * - useTranslations(<变量>) 动态命名空间绑定：运行时命名空间由调用方决定，无法静态归因，跳过
 * - showI18nToast 的 titleKey / descriptionKey / action.label：完整键引用，不走命名空间归因（由下方专用正则直接校验）
 *
 * 说明：`t('key', { fallback: '...' })` 的第二个参数只是 next-intl 的插值对象，
 * 不是兜底——use-intl 的 translateFn(key, values, formats, _fallback) 只有第 4 位置参数
 * 才是 fallback，且 TS 类型签名 (key, values?) 禁止该用法。因此所有 `t()` 调用一律纳入
 * 键存在性检查，不得因假 fallback 参数跳过（否则会漏检 Agent.fleet.builtin 类真实缺失）。
 */

import { readFileSync, readdirSync, statSync } from 'fs';
import { join, resolve, dirname } from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);
const rootDir = resolve(__dirname, '..');
const SRC_DIR = resolve(rootDir, 'src');
const EN_PATH = resolve(rootDir, 'locales/en.json');

const EXCLUDED_DIRS = new Set(['__tests__', '.next', 'node_modules', 'public']);
const EXCLUDED_FILE = /\.(test|spec)\.(ts|tsx|js|mjs)$/;
const SOURCE_EXT = /\.(ts|tsx)$/;

const KEY_RE = /^[A-Za-z0-9._-]+$/;

/** 收集翻译绑定：`const NAME = <useTranslations|getTranslations>(...)`。返回 { name, ns, offset, line }。 */
const BIND_USE_TRANSLATIONS_NS_RE =
  /const\s+([A-Za-z_$][\w$]*)\s*=\s*(?:await\s+)?useTranslations\s*\(\s*(['"])([^'"]+)\2\s*\)/g;
const BIND_USE_TRANSLATIONS_ROOT_RE = /const\s+([A-Za-z_$][\w$]*)\s*=\s*(?:await\s+)?useTranslations\s*\(\s*\)/g;
const BIND_USE_TRANSLATIONS_DYNAMIC_RE =
  /const\s+([A-Za-z_$][\w$]*)\s*=\s*(?:await\s+)?useTranslations\s*\(\s*([A-Za-z_$][\w$][^()]*?)\s*\)/g;
const BIND_GET_TRANSLATIONS_RE =
  /const\s+([A-Za-z_$][\w$]*)\s*=\s*(?:await\s+)?getTranslations\s*\(\s*\{\s*[^}]*namespace\s*:\s*(['"])([^'"]+)\2\s*\}/g;

/** 收集翻译调用：`NAME('key')` 与 `NAME('key', { values })`。仅当 NAME 存在绑定且是最近前驱时归因。 */
const CALL_RE = /([A-Za-z_$][\w$]*)\s*\(\s*(['"])([^'"]+)\2/g;

/** 判断源码是否存在可能的翻译调用（`t('key')` / `t("key")` 形态），用于无绑定文件的早期跳过判定。 */
const TRANSLATE_CALL_LIKE_RE = /\bt\s*\(\s*(['"])/;

/**
 * showI18nToast 第一参 titleKey / 第二参对象中 descriptionKey / action.label 均为完整 i18n 键。
 * 注意：showI18nToast 是从 services 导入的函数（非 useTranslations 绑定），不经过命名空间归因，
 * 直接按完整键校验；descriptionKey 仅匹配 showI18nToast 的 options 对象，避免误抓普通对象属性。
 * 三元表达式由 TERNARY_* 正则单独覆盖（`cond ? 'a' : 'b'`）：descriptionKey 与 action.label
 * 各有一组，提取 `?` 后 true 分支与 `:` 后 false 分支的键，比较操作数（如 === 'no_boards'）
 * 位于 `?` 前不提取。
 */
const SHOW_TOAST_TITLE_RE = /showI18nToast\s*\(\s*(['"])([^'"]+)\1/g;
const SHOW_TOAST_OPTIONS_RE = /showI18nToast\s*\([^;]*?descriptionKey\s*:\s*(['"])([^'"]+)\1/g;
const SHOW_TOAST_TERNARY_DESC_RE = /showI18nToast\s*\([^;]*?descriptionKey\s*:\s*[^,;})]*?\?\s*(['"])([^'"]+)\1\s*:\s*(['"])([^'"]+)\3/g;
const SHOW_TOAST_ACTION_RE = /showI18nToast\s*\([^;]*?action\s*:\s*\{\s*[^}]*?label\s*:\s*(['"])([^'"]+)\1/g;
const SHOW_TOAST_TERNARY_ACTION_RE =
  /showI18nToast\s*\([^;]*?action\s*:\s*\{\s*[^}]*?label\s*:\s*[^,;})]*?\?\s*(['"])([^'"]+)\1\s*:\s*(['"])([^'"]+)\3/g;

function collectSourceFiles(dir, out = []) {
  for (const entry of readdirSync(dir)) {
    const fullPath = join(dir, entry);
    if (EXCLUDED_DIRS.has(entry)) continue;
    const stat = statSync(fullPath);
    if (stat.isDirectory()) {
      collectSourceFiles(fullPath, out);
    } else if (SOURCE_EXT.test(entry) && !EXCLUDED_FILE.test(entry)) {
      out.push(fullPath);
    }
  }
  return out;
}

function lineOf(source, offset) {
  let line = 1;
  for (let i = 0; i < offset; i += 1) {
    if (source.charCodeAt(i) === 10) line += 1;
  }
  return line;
}

/** 解析单个 import 模块路径为绝对路径（仅本地源码：相对路径、@/ 别名），外部包返回 null。 */
const IMPORT_FROM_RE = /(?:import|export)[^'"]*?from\s*(['"])([^'"]+)\1/g;
const IMPORT_SIDE_EFFECT_RE = /^import\s*(['"])([^'"]+)\1/gm;

function resolveLocalPath(importPath, importerPath) {
  if (importPath.startsWith('@/')) {
    return resolve(SRC_DIR, importPath.slice(2));
  }
  if (importPath.startsWith('./') || importPath.startsWith('../')) {
    return resolve(dirname(importerPath), importPath);
  }
  return null; // 外部包 / 其他别名：不参与递归
}

const MODULE_EXT_CANDIDATES = ['.ts', '.tsx', '.js', '.jsx', '/index.ts', '/index.tsx', '/index.js', '/index.jsx'];

function resolveModuleFile(modulePath) {
  for (const candidate of MODULE_EXT_CANDIDATES) {
    const full = modulePath + candidate;
    try {
      if (statSync(full).isFile()) return full;
    } catch {
      // 继续尝试下一个候选
    }
  }
  return null;
}

/** 构建「目标文件绝对路径 → 真实引用方文件路径列表」映射（解析 import 语句），供无同名绑定文件递归继承命名空间。 */
function buildImporters(files, sourceByFile) {
  const importers = new Map();
  const addImporter = (importedFile, importerFile) => {
    if (!importers.has(importedFile)) importers.set(importedFile, []);
    importers.get(importedFile).push(importerFile);
  };
  for (const importerPath of files) {
    const source = sourceByFile.get(importerPath);
    const seen = new Set();
    for (const match of source.matchAll(IMPORT_FROM_RE)) {
      const importPath = match[2];
      if (seen.has(importPath)) continue;
      seen.add(importPath);
      const local = resolveLocalPath(importPath, importerPath);
      if (local == null) continue;
      const target = resolveModuleFile(local);
      if (target != null) addImporter(target, importerPath);
    }
    // side-effect import：`import './x.css'` 等
    for (const match of source.matchAll(IMPORT_SIDE_EFFECT_RE)) {
      const importPath = match[2];
      if (seen.has(importPath)) continue;
      seen.add(importPath);
      const local = resolveLocalPath(importPath, importerPath);
      if (local == null) continue;
      const target = resolveModuleFile(local);
      if (target != null) addImporter(target, importerPath);
    }
  }
  return importers;
}

function collectBindings(source) {
  const bindings = [];
  const record = (match, ns) => {
    const name = match[1];
    bindings.push({ name, ns, offset: match.index, line: lineOf(source, match.index) });
  };
  for (const match of source.matchAll(BIND_USE_TRANSLATIONS_NS_RE)) record(match, match[3]);
  for (const match of source.matchAll(BIND_USE_TRANSLATIONS_ROOT_RE)) record(match, '');
  // 动态命名空间（useTranslations(variable)）无法静态归因，ns 置 null 标记，t() 调用直接跳过。
  for (const match of source.matchAll(BIND_USE_TRANSLATIONS_DYNAMIC_RE)) record(match, null);
  for (const match of source.matchAll(BIND_GET_TRANSLATIONS_RE)) record(match, match[3]);
  return bindings;
}

function collectCalls(source) {
  const calls = [];
  for (const match of source.matchAll(CALL_RE)) {
    if (match[1] === 'showI18nToast') continue; // 由下方专用 RE 处理（完整键，非命名空间相对）
    calls.push({
      name: match[1],
      key: match[3],
      offset: match.index,
      line: lineOf(source, match.index),
    });
  }
  // showI18nToast 的 titleKey / descriptionKey / action.label 是完整键，不走命名空间归因。
  // 归因阶段识别 name === 'showI18nToast' 的调用时直接按完整键校验。
  for (const match of source.matchAll(SHOW_TOAST_TITLE_RE)) {
    calls.push({ name: 'showI18nToast', key: match[2], offset: match.index, line: lineOf(source, match.index) });
  }
  // 三元 descriptionKey：true/false 两个分支均为完整键引用
  for (const match of source.matchAll(SHOW_TOAST_TERNARY_DESC_RE)) {
    calls.push({ name: 'showI18nToast', key: match[2], offset: match.index, line: lineOf(source, match.index) });
    calls.push({ name: 'showI18nToast', key: match[4], offset: match.index, line: lineOf(source, match.index) });
  }
  for (const match of source.matchAll(SHOW_TOAST_OPTIONS_RE)) {
    calls.push({ name: 'showI18nToast', key: match[2], offset: match.index, line: lineOf(source, match.index) });
  }
  // 三元 action.label：true/false 两个分支均为完整键引用
  for (const match of source.matchAll(SHOW_TOAST_TERNARY_ACTION_RE)) {
    calls.push({ name: 'showI18nToast', key: match[2], offset: match.index, line: lineOf(source, match.index) });
    calls.push({ name: 'showI18nToast', key: match[4], offset: match.index, line: lineOf(source, match.index) });
  }
  for (const match of source.matchAll(SHOW_TOAST_ACTION_RE)) {
    calls.push({ name: 'showI18nToast', key: match[2], offset: match.index, line: lineOf(source, match.index) });
  }
  return calls;
}

function resolveEnKey(en, dottedPath) {
  let node = en;
  for (const part of dottedPath.split('.')) {
    if (node == null || typeof node !== 'object') return undefined;
    node = node[part];
  }
  return node;
}

/**
 * 沿真实 import 引用链收集「无同名绑定文件」调用方的翻译命名空间。
 * - importersByFile：目标文件绝对路径 → 引用该模块的文件路径列表（由 buildImporters 解析）
 * - callName：调用名（如 `t`），仅匹配同名绑定的命名空间，避免把 `tBilling` 等其他
 *   翻译函数混入候选（BuiltinToolsPanel 的 t 来自 props，但自身有 tBilling 绑定，
 *   此时 t 应继续向调用方递归，而不能归因到 billing.gates）
 * - 返回候选命名空间集合（根命名空间用空串表示），空集合表示无法解析（跳过该文件）。
 *
 * 采用 BFS + seen 防环：无固定深度上限，兼容多级 helper 转发链（如
 * DoctorPanel → AdvancedPanels → Panels → MemoryCommandCenter 的 4 层转发），
 * 避免 depth 截断造成漏检。
 */
function collectCallerNamespaces(filePath, importersByFile, bindingsByFile, sourceByFile, callName) {
  const namespaces = new Set();
  const seen = new Set([filePath]);
  const queue = [filePath];
  while (queue.length > 0) {
    const current = queue.shift();
    const local = (bindingsByFile.get(current) ?? []).filter((b) => b.name === callName);
    if (local.length > 0) {
      for (const b of local) namespaces.add(b.ns);
      continue;
    }
    for (const callerPath of importersByFile.get(current) ?? []) {
      if (seen.has(callerPath)) continue;
      seen.add(callerPath);
      // 调用方若把翻译绑定作为实参/JSX 属性传给当前模块（如 `resolveScopeNote(..., tHumanize)`、
      // `<Comp t={t} />`），说明当前模块的翻译函数参数来源确定，直接采用该绑定命名空间，
      // 比按同名 `t` 归因更精确（scopeNote.ts 的 t 实参是 tHumanize 而非 t）。
      const inferred = inferArgNamespaces(callerPath, bindingsByFile, sourceByFile);
      if (inferred.length > 0) {
        for (const ns of inferred) namespaces.add(ns);
        continue;
      }
      queue.push(callerPath);
    }
  }
  return [...namespaces];
}

/** 调用点实参推导：返回调用方源码中「作为函数实参或 JSX 属性值被使用的翻译绑定」命名空间集合。 */
function inferArgNamespaces(callerPath, bindingsByFile, sourceByFile) {
  const source = sourceByFile.get(callerPath);
  const bindings = bindingsByFile.get(callerPath) ?? [];
  if (bindings.length === 0) return [];
  const namespaces = new Set();
  for (const b of bindings) {
    // 作为函数调用实参：`f(a, tName)` / `f(tName)` 中 tName 是括号内独立实参标识符
    const argUse = new RegExp(`[,(]\\s*${b.name}\\b`);
    // 作为 JSX 属性值：`prop={tName}`（属性名任意，值绑定到翻译函数）
    const jsxUse = new RegExp(`=\\{\\s*${b.name}\\s*\\}`);
    if (argUse.test(source) || jsxUse.test(source)) namespaces.add(b.ns);
  }
  return [...namespaces];
}

const en = JSON.parse(readFileSync(EN_PATH, 'utf-8'));
const files = collectSourceFiles(SRC_DIR);
const missing = [];

// 全量源码只读一次，供 import 解析 / 绑定收集 / 调用收集复用，避免重复 IO。
const sourceByFile = new Map(files.map((filePath) => [filePath, readFileSync(filePath, 'utf-8')]));
// 预构建真实 import 引用映射（目标文件 → 引用方列表），供无同名绑定文件递归继承命名空间。
const importersByFile = buildImporters(files, sourceByFile);
// 预构建文件 → 翻译绑定映射（递归继承时查调用方绑定，避免重复解析）。
const bindingsByFile = new Map(files.map((filePath) => [filePath, collectBindings(sourceByFile.get(filePath))]));

for (const filePath of files) {
  const source = sourceByFile.get(filePath);
  const rel = filePath.replace(`${SRC_DIR}/`, 'src/');
  const bindings = bindingsByFile.get(filePath);
  // 无绑定文件也要扫描：props 传入的 t 可能调用翻译键（如 useAgentEditor 的 t('error')），
  // 需要通过递归继承调用方命名空间校验，不能直接跳过。
  const hasTranslateCallLike = TRANSLATE_CALL_LIKE_RE.test(source);
  if (bindings.length === 0 && !source.includes('showI18nToast') && !hasTranslateCallLike) continue;

  const calls = collectCalls(source);
  for (const call of calls) {
    if (call.name === 'showI18nToast') {
      // 完整键引用：不经命名空间归因，直接按完整键校验
      if (!KEY_RE.test(call.key)) continue; // 动态 key 无法静态验证
      if (resolveEnKey(en, call.key) === undefined) {
        missing.push({ file: rel, line: call.line, key: call.key });
      }
      continue;
    }
    // 最近前驱同名翻译绑定决定命名空间（JS 遮蔽语义）
    let ns = null;
    for (const binding of bindings) {
      if (binding.name === call.name && binding.offset < call.offset) ns = binding.ns;
    }
    if (ns !== null) {
      if (!KEY_RE.test(call.key)) continue; // 动态/非字面量键无法静态验证
      const fullKey = ns ? `${ns}.${call.key}` : call.key;
      if (resolveEnKey(en, fullKey) === undefined) {
        missing.push({ file: rel, line: call.line, key: fullKey });
      }
      continue;
    }
    // 无最近前驱绑定：helper 函数可能定义在翻译绑定之前（如 `function stateLabel(state, t)`
    // 声明于 `const t = useTranslations('ns')` 之前，运行时 t 由组件体内调用传入）。此时用
    // 文件内同名绑定的命名空间并集验证——任一候选命名空间存在该键即通过，避免误报。
    // 动态命名空间绑定（useTranslations(var)，ns=null）无法静态归因，先过滤。
    const candidateNs = [
      ...new Set(
        bindings
          .filter((b) => b.name === call.name)
          .map((b) => b.ns)
          .filter((ns) => ns !== null),
      ),
    ];
    if (candidateNs.length === 0) {
      // 文件内无同名绑定：可能是 props/参数传入的 t（如 useAgentEditor(id, isNew, t)），
      // 也可能是 useTranslations(<dynamicVar>) 动态命名空间（如 SchemaForm 的
      // translationNamespace prop，运行时命名空间由调用方决定，无法静态归因）。前者沿
      // import 引用链递归继承调用方的翻译命名空间（含根 ''），任一候选存在该键即通过；
      // 后者（存在同名绑定但 ns 全为 null）无法静态解析，跳过避免误报。
      if (call.name !== 't') continue; // 非翻译函数名（useSWR、fetch 等）跳过
      const dynamicOnly = bindings.some((b) => b.name === call.name && b.ns === null);
      if (dynamicOnly) continue;
      const callerNamespaces = collectCallerNamespaces(filePath, importersByFile, bindingsByFile, sourceByFile, call.name);
      if (callerNamespaces.length === 0) continue;
      if (!KEY_RE.test(call.key)) continue;
      const inherited = callerNamespaces.some((candidate) => {
        const fullKey = candidate ? `${candidate}.${call.key}` : call.key;
        return resolveEnKey(en, fullKey) !== undefined;
      });
      if (!inherited) {
        missing.push({
          file: rel,
          line: call.line,
          key: callerNamespaces.map((candidate) => (candidate ? `${candidate}.${call.key}` : call.key)).join(' | '),
        });
      }
      continue;
    }
    if (!KEY_RE.test(call.key)) continue;
    const resolved = candidateNs.some((candidate) => {
      const fullKey = candidate ? `${candidate}.${call.key}` : call.key;
      return resolveEnKey(en, fullKey) !== undefined;
    });
    if (!resolved) {
      missing.push({
        file: rel,
        line: call.line,
        key: candidateNs.map((candidate) => (candidate ? `${candidate}.${call.key}` : call.key)).join(' | '),
      });
    }
  }
}

missing.sort((a, b) => a.file.localeCompare(b.file) || a.line - b.line);

if (missing.length > 0) {
  console.error(`❌ 代码引用 ${missing.length} 个 en.json 中不存在的键（运行时显示原始 key）：`);
  for (const item of missing) {
    console.error(`   - ${item.file}:${item.line} -> ${item.key}`);
  }
  process.exit(1);
}
console.log(`✅ 代码引用检查通过（${files.length} 个文件，无缺失键引用）`);
