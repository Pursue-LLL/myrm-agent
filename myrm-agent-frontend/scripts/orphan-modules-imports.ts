/**
 * 孤儿扫描的 import 解析（纯函数，供 `orphan-modules-scan.ts` 调用，单测 `__tests__/orphan-modules-barrel.test.ts`）。
 *
 * 读出一个文件引用了哪些模块说明符、各自读取哪些名字，以及纯 barrel 的再导出表。读取的名字让可达性能精确到
 * barrel 的“哪一条再导出”：`import { A } from '@/x'` 只让 `x/index.ts` 里提供 `A` 的那一条再导出变活，
 * 其余再导出的模块仍可能是孤儿。无法确定读取了哪些名字的写法（命名空间导入、副作用导入、动态 `import()`、
 * `require()`、`new URL()`、无法识别的子句）一律按读取全部名字处理——宁可少报孤儿，也不误报。
 */

/** 读取模块的全部名字（与任何真实导出名都不冲突）。 */
export const ALL = '*';

export interface ImportRef {
  readonly specifier: string;
  /** 读取的名字：`default`、具名导出，或 `ALL`。 */
  readonly names: readonly string[];
}

export interface Reexport {
  readonly specifier: string;
  /** 在来源模块里的名字；`export * as ns from` 为 `ALL`。 */
  readonly imported: string;
}

export interface BarrelTable {
  /** 对外导出名 → 来源。 */
  readonly named: ReadonlyMap<string, Reexport>;
  /** `export * from` 的来源：无法在不解析来源的情况下知道它提供哪些名字。 */
  readonly stars: readonly string[];
}

export interface ParsedFile {
  readonly refs: readonly ImportRef[];
  /** 仅由再导出语句构成的 `index.ts(x)`；其余文件（含带代码的 `index.ts`）为 null。 */
  readonly barrel: BarrelTable | null;
}

/** 注释会被剥掉；字符串与模板字面量原样保留，以免把 `'http://x'` 里的 `//` 当成注释。 */
const COMMENT_OR_LITERAL = /\/\*[\s\S]*?\*\/|\/\/[^\n]*|'(?:\\.|[^'\\\n])*'|"(?:\\.|[^"\\\n])*"|`(?:\\.|[^`\\])*`/g;

const CLAUSE_FROM = /\b(?:import|export)\s+(?:type\s+)?([^;'"`]*?)\s*from\s*['"]([^'"]+)['"]/gs;
const OPAQUE_SPECIFIER_PATTERNS: readonly RegExp[] = [
  /\bimport\s*['"]([^'"]+)['"]/g,
  /\bimport\s*\(\s*['"]([^'"]+)['"]\s*\)/g,
  /\brequire\s*\(\s*['"]([^'"]+)['"]\s*\)/g,
  /\bnew\s+URL\(\s*['"]([^'"]+)['"]\s*,\s*import\.meta\.url/g,
];

const REEXPORT = /\bexport\s+(?:type\s+)?(?:\*(?:\s+as\s+([\w$]+))?|\{([^{}]*)\})\s*from\s*['"]([^'"]+)['"]\s*;?/g;
const DEFAULT_ONLY = /^[\w$]+$/;
const NAMED_ONLY = /^\{([^{}]*)\}$/;
const DEFAULT_AND_NAMED = /^[\w$]+\s*,\s*\{([^{}]*)\}$/;
const USE_CLIENT = /['"]use client['"]\s*;?/g;
const BARREL_FILE = /(?:^|\/)index\.tsx?$/;

export function stripComments(source: string): string {
  return source.replace(COMMENT_OR_LITERAL, (token) => (/^['"`]/.test(token) ? token : ' '));
}

interface Binding {
  readonly exported: string;
  readonly imported: string;
}

/** `a, b as c, type D` → 绑定列表；`type` 前缀只影响类型检查，不影响运行时可达性。 */
function bindingsOf(list: string): Binding[] {
  const bindings: Binding[] = [];
  for (const item of list.split(',')) {
    const parts = item
      .trim()
      .replace(/^type\s+/, '')
      .split(/\s+as\s+/)
      .map((part) => part.trim());
    const imported = parts[0];
    if (imported) {
      bindings.push({ imported, exported: parts[1] ?? imported });
    }
  }
  return bindings;
}

/** import/export 子句读取的名字；无法精确判定时返回 `[ALL]`。 */
function namesOfClause(clause: string): readonly string[] {
  const text = clause.trim();
  if (DEFAULT_ONLY.test(text)) {
    return ['default'];
  }
  const named = NAMED_ONLY.exec(text);
  const both = DEFAULT_AND_NAMED.exec(text);
  const listed = (named ?? both)?.[1];
  if (listed === undefined) {
    return [ALL];
  }
  const names = bindingsOf(listed).map((binding) => binding.imported);
  if (names.length === 0) {
    return [ALL];
  }
  return both ? ['default', ...names] : names;
}

function barrelTableOf(path: string, code: string): BarrelTable | null {
  if (!BARREL_FILE.test(path)) {
    return null;
  }
  const remainder = code
    .replace(REEXPORT, '')
    .replace(USE_CLIENT, '')
    .replace(/[\s;]+/g, '');
  if (remainder !== '') {
    return null;
  }
  const named = new Map<string, Reexport>();
  const stars: string[] = [];
  for (const match of code.matchAll(REEXPORT)) {
    const namespace: string | undefined = match[1];
    const list: string | undefined = match[2];
    const specifier = match[3];
    if (list !== undefined) {
      for (const { exported, imported } of bindingsOf(list)) {
        named.set(exported, { specifier, imported });
      }
    } else if (namespace !== undefined) {
      named.set(namespace, { specifier, imported: ALL });
    } else {
      stars.push(specifier);
    }
  }
  return { named, stars };
}

export function parseFile(path: string, source: string): ParsedFile {
  const code = stripComments(source);
  const refs: ImportRef[] = [];
  for (const [, clause, specifier] of code.matchAll(CLAUSE_FROM)) {
    refs.push({ specifier, names: namesOfClause(clause) });
  }
  for (const pattern of OPAQUE_SPECIFIER_PATTERNS) {
    for (const [, specifier] of code.matchAll(pattern)) {
      refs.push({ specifier, names: [ALL] });
    }
  }
  return { refs, barrel: barrelTableOf(path, code) };
}
