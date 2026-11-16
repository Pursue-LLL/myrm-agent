/**
 * E2E 测试通道静态扫描：找出产品代码里没有站在「非生产构建」守卫之后的 E2E 钩子。
 *
 * 测试通道是 E2E 工具链与产品共用的页面级接口：挂在 `window` 上的 store 句柄与诊断、`sessionStorage` 开关、
 * 自定义事件、运行时绑定脚本、开发桥组件。生产构建不该带它们——桌面发行版同样从回环地址提供页面，
 * 仅凭主机名区分不了开发与发行，所以守卫必须落在构建期常量 `process.env.NODE_ENV` 上，让打包器把整段
 * 分支连同其中的字符串一起删掉。
 *
 * 扫描对象是每一处「通道引用」：
 * - `global`：`__MYRM_*` / `__myrm*` / `__wikiMarkdownEditor` 这批全局名在运行时代码里的任何出现——成员读写
 *   `window.__myrmX`，也包括对象字面量的键与简写属性（`Object.assign(window, { __myrmX })`）、解构
 *   （`const { __myrmX } = window`）与裸标识符；类型位置的同名标识符（`declare global`、接口、类型别名、`as` 的
 *   目标类型）不是运行时引用；
 * - `string`：`e2e_*` 的存储键、`myrm-e2e-*` / `myrm_e2e_*` 的事件名与绑定前缀、`e2e-runtime-bootstrap` 脚本 id 与脚本地址，
 *   以字符串点名的同批全局（`Object.defineProperty(window, '__MYRM_…')`、`in` 判断），以及 `/…/test/…` 形态的
 *   测试接口路径（字符串字面量与模板字符串的静态片段都认；标识出现在更长的文本中间也认，例如内联脚本的正文）；
 * - `bridge`：开发桥组件的 JSX 挂载（`E2eBridgeLoader`、`E2ECompanionBridge`、`E2EChatBridge`、`E2EWikiBridge`）。
 *
 * 一处引用算「有守卫」，当且仅当它只会在非生产构建里被执行到，且这一点能从它的语法祖先上直接读出：
 * 它落在 `NODE_ENV !== 'production'` 为真的分支里；或落在 `&&` / `||` 的右侧；或前面有一条在生产构建里
 * 必然命中的提前返回。判定是过程内的——引用所在函数的调用方守卫不算，想让一个函数在生产里为空，守卫就写在这个
 * 函数里；守卫函数（`isLocalDevHost` 之类）也不算——打包器不会折叠跨模块调用，调用它们的分支会连同字符串留在
 * 生产包里，只有直接写出的 `process.env.NODE_ENV` 字面量才会被整段删掉。
 *
 * 静态资源（`public/`）是整份原样发布的文本（`sw.js` 由 Serwist 在构建时打包，按它的产物文本扫描），没有
 * 「守卫之后」可言：`findChannelTextLines` 给出资源文本里出现通道标识的行，出现即违规。
 */
import { type Node, visitorKeys } from 'oxc-parser';

import { jsxNameText, lineAt, parseProgram } from './source-ast';

export type E2eChannelKind = 'global' | 'string' | 'bridge';

export interface E2eChannelSite {
  /** 引用所在行（从 1 起）。 */
  line: number;
  kind: E2eChannelKind;
  /** 全局属性名、字符串字面量或开发桥组件名。 */
  name: string;
  /** 是否只会在非生产构建里被执行到。 */
  guarded: boolean;
}

/** `window` 上的测试句柄：E2E 的全局与 store 句柄（`__MYRM_E2E_*`、`__myrmChatStore`）和编辑器句柄。 */
const GLOBAL_NAME = /^(?:__MYRM|__myrm|__wikiMarkdownEditor$)/;
/**
 * 文本里的通道标识：同一批全局名、事件名与绑定前缀、脚本 id 与脚本地址，出现在文本的任何位置都算。
 * `__myrm_local_no_auth__` 这类产品哨兵值在 `__myrm` 后接下划线，不在其中。
 */
const CHANNEL_TOKEN = /__MYRM_|__myrm[A-Z]|__wikiMarkdownEditor|myrm[-_]e2e|e2e-runtime-bootstrap/;
/** 存储键只认 `e2e_` 开头：词中间的 `e2e_` 不是键，`e2ee_…` 之类的产品词也不是。 */
const STORAGE_KEY = /^e2e_/;
/** 静态资源是整份原样发布的文本，没有「守卫之后」可言；存储键前缀在这里也算。 */
const STATIC_ASSET_CHANNEL = new RegExp(`${CHANNEL_TOKEN.source}|\\be2e_`, 'g');
/** 只在非生产构建渲染的开发桥组件：两处挂载点渲染的加载器与伴侣桥，以及加载器再渲染的聊天桥与 Wiki 桥。 */
const BRIDGE_TAGS: ReadonlySet<string> = new Set([
  'E2eBridgeLoader',
  'E2ECompanionBridge',
  'E2EChatBridge',
  'E2EWikiBridge',
]);
/** 产品代码不该引用的测试接口路径（例如 `/security/allowlist/test/hitl-probe`）。 */
const TEST_ROUTE = /\/test\//;
const COMPARISONS: ReadonlySet<string> = new Set(['===', '!==', '==', '!=']);

function unwrap(node: Node): Node {
  return node.type === 'ParenthesizedExpression' ? unwrap(node.expression) : node;
}

function isNodeEnv(node: Node): boolean {
  const member = unwrap(node);
  if (member.type !== 'MemberExpression' || member.computed || member.property.type !== 'Identifier') {
    return false;
  }
  const env = unwrap(member.object);
  return (
    member.property.name === 'NODE_ENV' &&
    env.type === 'MemberExpression' &&
    !env.computed &&
    env.property.type === 'Identifier' &&
    env.property.name === 'env' &&
    env.object.type === 'Identifier' &&
    env.object.name === 'process'
  );
}

function isProductionLiteral(node: Node): boolean {
  const literal = unwrap(node);
  return literal.type === 'Literal' && literal.value === 'production';
}

/** `NODE_ENV` 与 `'production'` 的比较：返回运算符，其余表达式返回 null。 */
function productionComparison(node: Node): string | null {
  if (node.type !== 'BinaryExpression' || !COMPARISONS.has(node.operator)) {
    return null;
  }
  const sides = [node.left, node.right];
  return sides.some(isNodeEnv) && sides.some(isProductionLiteral) ? node.operator : null;
}

/** 条件为真时一定不是生产构建。 */
function excludesProduction(node: Node): boolean {
  const condition = unwrap(node);
  switch (condition.type) {
    case 'BinaryExpression':
      return productionComparison(condition)?.startsWith('!') ?? false;
    case 'LogicalExpression':
      return condition.operator === '&&'
        ? excludesProduction(condition.left) || excludesProduction(condition.right)
        : condition.operator === '||' && excludesProduction(condition.left) && excludesProduction(condition.right);
    case 'UnaryExpression':
      return condition.operator === '!' && coversProduction(condition.argument);
    default:
      return false;
  }
}

/** 生产构建里条件一定为真（条件为假时一定不是生产构建）。 */
function coversProduction(node: Node): boolean {
  const condition = unwrap(node);
  switch (condition.type) {
    case 'BinaryExpression':
      return productionComparison(condition)?.startsWith('=') ?? false;
    case 'LogicalExpression':
      return condition.operator === '||'
        ? coversProduction(condition.left) || coversProduction(condition.right)
        : condition.operator === '&&' && coversProduction(condition.left) && coversProduction(condition.right);
    case 'UnaryExpression':
      return condition.operator === '!' && excludesProduction(condition.argument);
    default:
      return false;
  }
}

function returns(statement: Node): boolean {
  return (
    statement.type === 'ReturnStatement' ||
    (statement.type === 'BlockStatement' && statement.body.some((inner) => inner.type === 'ReturnStatement'))
  );
}

/** 语句列表里排在 `child` 之前的某条提前返回，在生产构建里必然命中。 */
function earlyReturnBefore(statements: readonly Node[], child: Node): boolean {
  const index = statements.indexOf(child);
  return statements
    .slice(0, Math.max(index, 0))
    .some(
      (statement) =>
        statement.type === 'IfStatement' && coversProduction(statement.test) && returns(statement.consequent),
    );
}

/** `child` 沿着 `parent` 这一层是否只会在非生产构建里被执行到。 */
function guardedBy(parent: Node, child: Node): boolean {
  switch (parent.type) {
    case 'IfStatement':
    case 'ConditionalExpression':
      return (
        (parent.consequent === child && excludesProduction(parent.test)) ||
        (parent.alternate === child && coversProduction(parent.test))
      );
    case 'LogicalExpression':
      return (
        parent.right === child &&
        (parent.operator === '&&'
          ? excludesProduction(parent.left)
          : parent.operator === '||' && coversProduction(parent.left))
      );
    case 'BlockStatement':
    case 'Program':
      return earlyReturnBefore(parent.body, child);
    default:
      return false;
  }
}

function isGuarded(node: Node, ancestors: readonly Node[]): boolean {
  let child = node;
  for (let depth = ancestors.length - 1; depth >= 0; depth -= 1) {
    const parent = ancestors[depth];
    if (guardedBy(parent, child)) {
      return true;
    }
    child = parent;
  }
  return false;
}

function memberName(node: Node): string | null {
  if (node.type !== 'MemberExpression') {
    return null;
  }
  if (!node.computed) {
    return node.property.type === 'Identifier' ? node.property.name : null;
  }
  return node.property.type === 'Literal' && typeof node.property.value === 'string' ? node.property.value : null;
}

function isChannelText(text: string): boolean {
  return CHANNEL_TOKEN.test(text) || STORAGE_KEY.test(text) || TEST_ROUTE.test(text);
}

/** 值与类型之间只做断言的包装：节点仍在运行时执行，其余 `TS*` 祖先都表示这是类型位置。 */
const RUNTIME_TS_WRAPPERS: ReadonlySet<string> = new Set([
  'TSAsExpression',
  'TSSatisfiesExpression',
  'TSNonNullExpression',
  'TSTypeAssertion',
  'TSInstantiationExpression',
]);

function inTypePosition(ancestors: readonly Node[]): boolean {
  return ancestors.some((ancestor) => ancestor.type.startsWith('TS') && !RUNTIME_TS_WRAPPERS.has(ancestor.type));
}

/** 这个节点若是一处通道引用，返回它的种类与名字；`ancestors` 是从根到它的父节点的祖先链。 */
function channelReference(node: Node, ancestors: readonly Node[]): { kind: E2eChannelKind; name: string } | null {
  const parent = ancestors[ancestors.length - 1];
  if (node.type === 'MemberExpression') {
    const name = memberName(node);
    return name !== null && GLOBAL_NAME.test(name) ? { kind: 'global', name } : null;
  }
  if (node.type === 'Identifier') {
    // 成员访问的属性名已由 MemberExpression 记过；简写属性的键与值是同一处源码，只记值。
    const memberProperty = parent?.type === 'MemberExpression' && parent.property === node && !parent.computed;
    const shorthandKey = parent?.type === 'Property' && parent.shorthand && parent.key === node;
    return GLOBAL_NAME.test(node.name) && !memberProperty && !shorthandKey && !inTypePosition(ancestors)
      ? { kind: 'global', name: node.name }
      : null;
  }
  if (node.type === 'Literal') {
    // 类型位置的字符串不是运行时引用；`window['__myrm…']` 的键已经按成员访问记过一次。
    const typePosition = parent?.type === 'TSLiteralType';
    const memberKey = parent?.type === 'MemberExpression' && parent.computed && parent.property === node;
    return typeof node.value === 'string' && isChannelText(node.value) && !typePosition && !memberKey
      ? { kind: 'string', name: node.value }
      : null;
  }
  if (node.type === 'TemplateElement') {
    const text = node.value.cooked ?? node.value.raw;
    return isChannelText(text) ? { kind: 'string', name: text } : null;
  }
  if (node.type === 'JSXOpeningElement') {
    const name = jsxNameText(node.name);
    return BRIDGE_TAGS.has(name) ? { kind: 'bridge', name } : null;
  }
  return null;
}

function isNode(value: unknown): value is Node {
  return typeof value === 'object' && value !== null && typeof (value as { type?: unknown }).type === 'string';
}

function walk(node: Node, ancestors: Node[], visit: (node: Node, ancestors: readonly Node[]) => void): void {
  visit(node, ancestors);
  const record = node as unknown as Record<string, unknown>;
  ancestors.push(node);
  for (const key of visitorKeys[node.type] ?? []) {
    const value = record[key];
    for (const child of Array.isArray(value) ? value : [value]) {
      if (isNode(child)) {
        walk(child, ancestors, visit);
      }
    }
  }
  ancestors.pop();
}

/** 返回源码里全部通道引用（含是否有守卫），按出现顺序。 */
export function scanE2eChannelSites(source: string, fileName: string): E2eChannelSite[] {
  const sites: E2eChannelSite[] = [];
  walk(parseProgram(source, fileName), [], (node, ancestors) => {
    const reference = channelReference(node, ancestors);
    if (reference !== null) {
      sites.push({ line: lineAt(source, node.start), ...reference, guarded: isGuarded(node, ancestors) });
    }
  });
  return sites;
}

/** 没有守卫的通道引用：生产构建里会带上它们。 */
export function findUnguardedE2eChannelSites(source: string, fileName: string): E2eChannelSite[] {
  return scanE2eChannelSites(source, fileName).filter((site) => !site.guarded);
}

/** 静态资源文本里出现通道标识的行号（从 1 起，每行一次）；资源整份原样发布，出现即违规。 */
export function findChannelTextLines(source: string): number[] {
  const lines = new Set<number>();
  for (const hit of source.matchAll(STATIC_ASSET_CHANNEL)) {
    lines.add(lineAt(source, hit.index));
  }
  return [...lines];
}

/** 把导入路径解析成相对前端根目录的 `src/…` 路径；包名等非本地路径返回 null。 */
function resolveLocalImport(fromFile: string, specifier: string): string | null {
  if (specifier.startsWith('@/')) {
    return `src/${specifier.slice(2)}`;
  }
  if (!specifier.startsWith('.')) {
    return null;
  }
  const segments = fromFile.split('/').slice(0, -1);
  for (const part of specifier.split('/')) {
    if (part === '..') {
      segments.pop();
    } else if (part !== '.') {
      segments.push(part);
    }
  }
  return segments.join('/');
}

/** 开发桥目录里只有这个叶子模块可以被产品代码导入：它不依赖任何 store 或 lib，且在生产构建里恒为假。 */
const IMPORTABLE_DEV_MODULE = 'src/components/dev/localDevHost';

/**
 * 产品文件对开发桥目录（`src/components/dev/`）的导入：`localDevHost` 之外的每一处，
 * 都会把开发桥的模块图拉进生产构建，除非导入点本身被打包器剪掉。返回导入路径原文。
 */
export function findDevBridgeImports(source: string, fileName: string): string[] {
  const specifiers: string[] = [];
  walk(parseProgram(source, fileName), [], (node) => {
    const target =
      node.type === 'ImportDeclaration' ||
      node.type === 'ImportExpression' ||
      node.type === 'ExportAllDeclaration' ||
      node.type === 'ExportNamedDeclaration'
        ? node.source
        : null;
    if (target?.type !== 'Literal' || typeof target.value !== 'string') {
      return;
    }
    const resolved = resolveLocalImport(fileName, target.value);
    if (resolved?.startsWith('src/components/dev/') && resolved !== IMPORTABLE_DEV_MODULE) {
      specifiers.push(target.value);
    }
  });
  return specifiers;
}
