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
 * - showI18nToast('key', ...) / translateI18nKey('key', ...) → 完整键 key
 *
 * 归因策略：以「最近前驱同名绑定」关联调用与命名空间——组件内 `const t = ...`
 * 的遮蔽天然形成作用域边界，无需完整 JS 解析器；动态 key（模板串/变量）无法
 * 静态 resolve，跳过（运行时仍会显示 key 本身，但不属于本门禁可静态判定的范围）。
 *
 * 排除项：
 * - __tests__ / *.test.* / *.spec.*：测试文件用 mock translator，不产生真实 UI 引用
 * - .next / node_modules / public / scripts：非运行时源码
 * - useTranslations(dynamicVar) / getTranslations({ namespace: dynamicVar })：无法静态归因
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

/**
 * 临时豁免键：AgentSecurityTab 由并行开发者正在重构，其 injectionPolicy 区块
 * 使用 `{ default: '...' }` 参数（next-intl 不将其作为 fallback，缺键仍显示原始
 * key）。待并行开发者补上 en.json 键后，本豁免自动失效（键存在即不再报缺）。
 */
const SKIP_KEYS = new Set(['agent.security.injectionPolicyTitle', 'agent.security.injectionPolicyDesc']);

/** 校验 key 形如合法 i18n 路径（字母/数字/点/下划线/连字符），排除 CSS 类、任意字符串。 */
const KEY_RE = /^[A-Za-z0-9._-]+$/;

/** 收集翻译绑定：`const NAME = <useTranslations|getTranslations>(...)`。返回 { name, ns, offset, line }。 */
const BIND_USE_TRANSLATIONS_NS_RE =
  /const\s+([A-Za-z_$][\w$]*)\s*=\s*(?:await\s+)?useTranslations\s*\(\s*(['"])([^'"]+)\2\s*\)/g;
const BIND_USE_TRANSLATIONS_ROOT_RE = /const\s+([A-Za-z_$][\w$]*)\s*=\s*(?:await\s+)?useTranslations\s*\(\s*\)/g;
const BIND_GET_TRANSLATIONS_RE =
  /const\s+([A-Za-z_$][\w$]*)\s*=\s*(?:await\s+)?getTranslations\s*\(\s*\{\s*[^}]*namespace\s*:\s*(['"])([^'"]+)\1\s*\}/g;

/** 收集翻译调用：`NAME('key')` 与 `NAME('key', { values })`。仅当 NAME 存在绑定且是最近前驱时归因。 */
const CALL_RE = /([A-Za-z_$][\w$]*)\s*\(\s*(['"])([^'"]+)\2/g;

/** showI18nToast 第一参与 descriptionKey / action.label 均为完整 i18n 键。 */
const SHOW_TOAST_RE =
  /showI18nToast\s*\(\s*(['"])([^'"]+)\1|descriptionKey\s*:\s*(['"])([^'"]+)\3|action\s*:\s*\{\s*label\s*:\s*(['"])([^'"]+)\5/g;

/** next-intl t() 的第二参数 `{ fallback: '...' }`：缺键时返回 fallback，而非 MISSING_MESSAGE。 */
const HAS_FALLBACK_RE = /fallback\s*:/;

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

/** 从调用位置向后扫描到首个平衡 `)`，返回其后的剩余文本（不含字符串/注释）。 */
function callHasFallback(source, callStart) {
  let depth = 0;
  let inString = null;
  for (let i = callStart; i < source.length; i += 1) {
    const ch = source[i];
    if (inString) {
      if (ch === '\\') i += 1;
      else if (ch === inString) inString = null;
      continue;
    }
    if (ch === '"' || ch === "'" || ch === '`') {
      inString = ch;
      continue;
    }
    if (ch === '(') depth += 1;
    else if (ch === ')') {
      depth -= 1;
      if (depth === 0) return HAS_FALLBACK_RE.test(source.slice(callStart, i));
    }
  }
  return false;
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
    if (callHasFallback(source, match.index)) continue; // fallback 兜底，无 MISSING_MESSAGE
    calls.push({
      name: match[1],
      key: match[3],
      offset: match.index,
      line: lineOf(source, match.index),
    });
  }
  for (const match of source.matchAll(SHOW_TOAST_RE)) {
    const key = match[2] ?? match[4] ?? match[6];
    calls.push({
      name: 'showI18nToast',
      key,
      offset: match.index,
      line: lineOf(source, match.index),
    });
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
  const bindings = collectBindings(source);
  if (bindings.length === 0 && !source.includes('showI18nToast')) continue;

  const calls = collectCalls(source);
  for (const call of calls) {
    // 最近前驱同名翻译绑定决定命名空间（JS 遮蔽语义）
    let ns = null;
    for (const binding of bindings) {
      if (binding.name === call.name && binding.offset < call.offset) ns = binding.ns;
    }
    if (ns === null) continue; // 无翻译绑定：可能是普通函数调用，不归因
    if (!KEY_RE.test(call.key)) continue; // 动态/非字面量键无法静态验证
    const fullKey = ns ? `${ns}.${call.key}` : call.key;
    if (SKIP_KEYS.has(fullKey)) continue; // 并行开发豁免
    if (resolveEnKey(en, fullKey) === undefined) {
      missing.push({
        file: filePath.replace(`${SRC_DIR}/`, 'src/'),
        line: call.line,
        key: fullKey,
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
