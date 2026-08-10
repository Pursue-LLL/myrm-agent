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
 * 排除项：
 * - __tests__ / *.test.* / *.spec.*：测试文件用 mock translator，不产生真实 UI 引用
 * - .next / node_modules / public / scripts：非运行时源码
 * - useTranslations(dynamicVar) / getTranslations({ namespace: dynamicVar })：无法静态归因
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
const BIND_GET_TRANSLATIONS_RE =
  /const\s+([A-Za-z_$][\w$]*)\s*=\s*(?:await\s+)?getTranslations\s*\(\s*\{\s*[^}]*namespace\s*:\s*(['"])([^'"]+)\1\s*\}/g;

/** 收集翻译调用：`NAME('key')` 与 `NAME('key', { values })`。仅当 NAME 存在绑定且是最近前驱时归因。 */
const CALL_RE = /([A-Za-z_$][\w$]*)\s*\(\s*(['"])([^'"]+)\2/g;

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

function collectBindings(source) {
  const bindings = [];
  const record = (match) => {
    const name = match[1];
    const ns = match[3] ?? ''; // 根 useTranslations() 的 ns 为空串
    bindings.push({ name, ns, offset: match.index, line: lineOf(source, match.index) });
  };
  for (const match of source.matchAll(BIND_USE_TRANSLATIONS_NS_RE)) record(match);
  for (const match of source.matchAll(BIND_USE_TRANSLATIONS_ROOT_RE)) record(match);
  for (const match of source.matchAll(BIND_GET_TRANSLATIONS_RE)) record(match);
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

const en = JSON.parse(readFileSync(EN_PATH, 'utf-8'));
const files = collectSourceFiles(SRC_DIR);
const missing = [];

for (const filePath of files) {
  const source = readFileSync(filePath, 'utf-8');
  const rel = filePath.replace(`${SRC_DIR}/`, 'src/');
  const bindings = collectBindings(source);
  if (bindings.length === 0 && !source.includes('showI18nToast')) continue;

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
    // 文件内同名绑定的命名空间并集验证——任一候选命名空间存在该键即通过，避免误报；文件内
    // 无同名绑定（props 传入的 t）自动跳过。
    const candidateNs = [...new Set(bindings.filter((b) => b.name === call.name).map((b) => b.ns))];
    if (candidateNs.length === 0) continue;
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
