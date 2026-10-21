/**
 * 孤儿模块静态扫描（纯函数，无文件系统访问；供 `check-orphan-modules.mjs` 调用，单测 `__tests__/orphan-modules-scan.test.ts`）。
 *
 * 孤儿 = 从产品入口出发沿生产 import 边不可达的 `src/` 模块。单元测试 import 被测文件，所以孤儿的测试照样绿，
 * 测试绿不等于代码活着。口径：
 * - 入口（根）：`src/app/**`（路由与 layout/page/route/sw 等约定文件）、`src/middleware.ts` 等根约定文件、`.d.ts` 与生成物，
 *   以及被 `src/` 之外的构建配置与脚本引用的模块（`next.config.ts` 的插件路径、脚本的相对 import 等）；
 * - 沿根的生产 import 边求可达闭包：只被孤儿引用的模块同样是孤儿，一次报全，不会删一层又冒出一层；
 * - 测试文件与 `src/test-utils/` 既不是候选也不是消费者——测试 import 不能让被测代码“活着”；
 * - barrel（纯再导出的 `index.ts`）只是绑定、不是消费者：没人 import 的 barrel 不会让它再导出的模块变活，它自己也算孤儿；
 *   barrel 被 import 时，只有被点名的名字对应的那条再导出变活（`import { A } from '@/x'` 不会拖活 `x/index.ts` 里其余再导出）。
 *
 * 判定读真实模块说明符（`import … from` / 副作用 `import` / 动态 `import()` / `require()` / `new URL(…, import.meta.url)`），
 * 且先剥掉注释：按文件名子串匹配会命中同名标识符，注释里的示例 import 也不是消费者。
 * 没有基线、没有豁免标记：孤儿要么接入入口，要么连同测试、文档行、i18n 键一起删除。
 */
import { posix } from 'node:path';

import { ALL, type BarrelTable, parseFile, stripComments } from './orphan-modules-imports';

export interface SourceFile {
  /** 相对项目根的 posix 路径，如 `src/lib/x.ts`。 */
  readonly path: string;
  readonly source: string;
}

export interface OrphanScanInput {
  /** `src/` 下全部 `.ts` / `.tsx`（含测试，由扫描器自行分类）。 */
  readonly srcFiles: readonly SourceFile[];
  /** `src/` 之外的消费者：构建配置与脚本。 */
  readonly consumerFiles: readonly SourceFile[];
}

export interface OrphanScanResult {
  /** 参与判定的候选模块数（自检用：为 0 说明路径或解析器失效）。 */
  readonly scanned: number;
  readonly orphans: readonly string[];
}

/** Next.js 在 `src/` 根按文件名约定装载的入口；`src/app/**` 下的约定文件由前缀规则覆盖。 */
const ROOT_CONVENTION_ENTRIES: ReadonlySet<string> = new Set([
  'src/middleware.ts',
  'src/middleware.tsx',
  'src/instrumentation.ts',
  'src/instrumentation-client.ts',
]);

const GENERATED_ENTRY = /(?:^|\/)litellmRouting\.generated\.ts$/;
const TEST_FILE = /(?:^|\/)(?:__tests__|__mocks__)\/|\.(?:test|spec)\.tsx?$/;
const TEST_SUPPORT_DIR = 'src/test-utils/';

const STRING_LITERAL = /(['"`])([^'"`\n]+)\1/g;

/** 一个模块引用另一个模块读取的名字。 */
interface ResolvedRef {
  readonly target: string;
  readonly names: readonly string[];
}

interface ResolvedReexport {
  readonly target: string;
  /** 在来源模块里的名字。 */
  readonly imported: string;
}

interface ResolvedBarrel {
  readonly named: ReadonlyMap<string, ResolvedReexport>;
  readonly stars: readonly string[];
}

interface ModuleNode {
  readonly refs: readonly ResolvedRef[];
  readonly barrel: ResolvedBarrel | null;
}

export function isTestSupportFile(path: string): boolean {
  return TEST_FILE.test(path) || path.startsWith(TEST_SUPPORT_DIR);
}

function isEntryFile(path: string): boolean {
  return (
    path.startsWith('src/app/') ||
    path.endsWith('.d.ts') ||
    GENERATED_ENTRY.test(path) ||
    ROOT_CONVENTION_ENTRIES.has(path)
  );
}

/** 把 `base`（无扩展名的模块路径）解析成已知源文件：本身、`.ts`、`.tsx`、目录 index。 */
function resolveModule(base: string, known: ReadonlySet<string>): string | null {
  for (const candidate of [base, `${base}.ts`, `${base}.tsx`, `${base}/index.ts`, `${base}/index.tsx`]) {
    if (known.has(candidate)) {
      return candidate;
    }
  }
  return null;
}

/** 解析 `src/` 内模块的说明符；第三方包与未知路径返回 null。 */
function resolveSpecifier(specifier: string, fromPath: string, known: ReadonlySet<string>): string | null {
  if (specifier.startsWith('@/')) {
    return resolveModule(`src/${specifier.slice(2)}`, known);
  }
  if (specifier.startsWith('.')) {
    return resolveModule(posix.normalize(posix.join(posix.dirname(fromPath), specifier)), known);
  }
  return null;
}

/** 构建配置与脚本引用 `src/` 的写法很杂（插件路径字符串、相对 import、`./src/x`），统一按字符串字面量解析。 */
function consumerTargets(file: SourceFile, known: ReadonlySet<string>): string[] {
  const targets: string[] = [];
  for (const match of stripComments(file.source).matchAll(STRING_LITERAL)) {
    const literal = match[2];
    const resolved =
      resolveSpecifier(literal, file.path, known) ??
      resolveModule(posix.normalize(literal.replace(/^\.\//, '')), known);
    if (resolved) {
      targets.push(resolved);
    }
  }
  return targets;
}

function resolveBarrel(table: BarrelTable, fromPath: string, known: ReadonlySet<string>): ResolvedBarrel {
  const named = new Map<string, ResolvedReexport>();
  for (const [exported, { specifier, imported }] of table.named) {
    const target = resolveSpecifier(specifier, fromPath, known);
    if (target) {
      named.set(exported, { target, imported });
    }
  }
  const stars = table.stars.flatMap((specifier) => resolveSpecifier(specifier, fromPath, known) ?? []);
  return { named, stars };
}

function moduleNode(file: SourceFile, known: ReadonlySet<string>): ModuleNode {
  const parsed = parseFile(file.path, file.source);
  const refs: ResolvedRef[] = [];
  for (const { specifier, names } of parsed.refs) {
    const target = resolveSpecifier(specifier, file.path, known);
    if (target) {
      refs.push({ target, names });
    }
  }
  return { refs, barrel: parsed.barrel && resolveBarrel(parsed.barrel, file.path, known) };
}

/** 读取 barrel 的 `name` 时被拖活的 `[模块, 名字]`：全部名字对应全部再导出，具名则只对应提供该名字的那条。 */
function followBarrel(barrel: ResolvedBarrel, name: string): Array<readonly [string, string]> {
  if (name === ALL) {
    return [
      ...[...barrel.named.values()].map(({ target, imported }) => [target, imported] as const),
      ...barrel.stars.map((target) => [target, ALL] as const),
    ];
  }
  const entry = barrel.named.get(name);
  return entry ? [[entry.target, entry.imported]] : barrel.stars.map((target) => [target, name] as const);
}

/**
 * 从根出发的可达模块。只有 barrel 区分读取的名字；普通模块被读取任何名字都会沿它的全部 import 边继续。
 */
function reachableModules(roots: readonly string[], graph: ReadonlyMap<string, ModuleNode>): ReadonlySet<string> {
  const followed = new Map<string, Set<string>>();
  const pending: Array<readonly [string, string]> = roots.map((root) => [root, ALL] as const);
  while (pending.length > 0) {
    const [path, name] = pending.pop() as readonly [string, string];
    const node = graph.get(path);
    const key = node?.barrel ? name : ALL;
    const seen = followed.get(path) ?? new Set<string>();
    followed.set(path, seen);
    if (seen.has(key)) {
      continue;
    }
    seen.add(key);
    if (node?.barrel) {
      pending.push(...followBarrel(node.barrel, name));
    } else if (node) {
      for (const { target, names } of node.refs) {
        pending.push(...names.map((imported) => [target, imported] as const));
      }
    }
  }
  return new Set(followed.keys());
}

export function findOrphanModules({ srcFiles, consumerFiles }: OrphanScanInput): OrphanScanResult {
  const production = srcFiles.filter((file) => !isTestSupportFile(file.path));
  const known: ReadonlySet<string> = new Set(srcFiles.map((file) => file.path));

  const graph = new Map<string, ModuleNode>(production.map((file) => [file.path, moduleNode(file, known)]));
  const reachable = reachableModules(
    [
      ...production.filter((file) => isEntryFile(file.path)).map((file) => file.path),
      ...consumerFiles.flatMap((file) => consumerTargets(file, known)),
    ],
    graph,
  );

  const candidates = production.filter((file) => !isEntryFile(file.path));
  return {
    scanned: candidates.length,
    orphans: candidates
      .map((file) => file.path)
      .filter((path) => !reachable.has(path))
      .sort(),
  };
}
