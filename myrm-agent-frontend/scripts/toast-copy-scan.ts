/**
 * Toast 文案静态扫描：找出 `toast` 调用里写死的用户可见文案。
 *
 * 为什么需要：`hardcoded-copy-scan.ts` 只看 TSX 里的 JSX，toast 消息写在事件处理 / store / 工具函数里，
 * 同样会让其余语言的用户看到中文或英文原文，且类型检查、单测都发现不了。
 *
 * 扫描对象（oxc-parser 语法树，`.ts` 与 `.tsx` 都扫）：
 * - `toast(...)` / `toast.success|error|info|warning|message|loading(...)` 的消息参数；
 * - 对象形式的 `title` / `description`、选项里的 `description` 与 `action` / `cancel` 的 `label`，
 *   以及 `toast.promise` 的 `loading` / `success` / `error`；
 * - 消息里的字面量分支：`err.message || 'x'`、三元、`??`，以及模板字符串里 `${}` 内的同类分支；
 *   翻译函数后面的兜底（`t('key') || 'x'`）也在其中——next-intl 的 `t` 缺键时返回键路径、从不返回空值，
 *   兜底永远不会执行，只会让人误以为缺键时有保护。
 *
 * toast 里出现的任何文字都面向用户，所以含一个字母（含 CJK）即判为文案，`'Copied'` 这类单词也不放过。
 *
 * 识别的调用对象：`toast`、`import { toast as alias }` 的别名，以及 `useGlobalEvents` 里与 toast 签名一致的转发对象 `pushToast`。
 * 不覆盖：先赋给变量再传入的文案（`const msg = '…'; toast(msg)`），以及经其它封装函数转发的 toast。
 */
import {
  type Argument,
  type CallExpression,
  type Expression,
  type ObjectPropertyKind,
  type Program,
  Visitor,
} from 'oxc-parser';

import { renderedLiterals, staticText } from './hardcoded-copy-scan';
import { lineAt, parseProgram } from './source-ast';

export interface ToastCopySite {
  line: number;
  text: string;
}

/** 带消息参数的 toast 方法；`dismiss` 等不在其中。 */
const MESSAGE_METHODS = new Set(['success', 'error', 'info', 'warning', 'message', 'loading']);
/** 对象形式与选项参数里承载文案的属性。 */
const COPY_PROPERTIES = new Set(['title', 'description']);
/** `toast.promise` 的三种状态文案。 */
const PROMISE_PROPERTIES = new Set(['loading', 'success', 'error']);
const PROMISE_COPY_PROPERTIES = new Set([...COPY_PROPERTIES, ...PROMISE_PROPERTIES]);
/** 承载文案的属性里再嵌一层 `{ label }` 的按钮。 */
const BUTTON_PROPERTIES = new Set(['action', 'cancel']);
/** 与 toast 签名一致的转发对象（`useGlobalEvents` 里按开关决定是否真正弹出）；名字必须含 "toast"，见 `MENTIONS_TOAST`。 */
const FORWARDING_RECEIVERS = ['pushToast'];
/** 所有接收者要么是 `toast`、要么由 `import { toast … }` 引入、要么是上面的转发对象，源码里必然出现 "toast"；不含的文件免于解析。 */
const MENTIONS_TOAST = /toast/i;
const HAS_LETTER = /\p{L}/u;

interface ToastCall {
  isPromise: boolean;
}

interface NamedProperty {
  name: string;
  value: Expression;
}

/** `{ name: value }` 形式的属性（键是标识符或字符串）；简写、方法、访问器、展开与计算键都不是。 */
function namedProperty(property: ObjectPropertyKind): NamedProperty | null {
  if (
    property.type !== 'Property' ||
    property.kind !== 'init' ||
    property.method ||
    property.shorthand ||
    property.computed
  ) {
    return null;
  }
  const { key, value } = property;
  if (key.type === 'Identifier') {
    return { name: key.name, value };
  }
  return key.type === 'Literal' && typeof key.value === 'string' ? { name: key.value, value } : null;
}

/** 本文件里指向 toast 的名字：`toast` 本身、`import { toast as alias }` 的别名，以及转发对象。 */
function toastReceivers(program: Program): Set<string> {
  const receivers = new Set(['toast', ...FORWARDING_RECEIVERS]);
  for (const statement of program.body) {
    if (statement.type !== 'ImportDeclaration') {
      continue;
    }
    for (const specifier of statement.specifiers) {
      if (specifier.type !== 'ImportSpecifier') {
        continue;
      }
      const imported = specifier.imported.type === 'Identifier' ? specifier.imported.name : specifier.imported.value;
      if (imported === 'toast') {
        receivers.add(specifier.local.name);
      }
    }
  }
  return receivers;
}

export function findToastCopySites(source: string, fileName = 'source.tsx'): ToastCopySite[] {
  if (!MENTIONS_TOAST.test(source)) {
    return [];
  }
  const program = parseProgram(source, fileName);
  const receivers = toastReceivers(program);
  const sites: ToastCopySite[] = [];

  const toastCall = (callee: Expression): ToastCall | null => {
    if (callee.type === 'Identifier') {
      return receivers.has(callee.name) ? { isPromise: false } : null;
    }
    if (
      callee.type !== 'MemberExpression' ||
      callee.computed ||
      callee.object.type !== 'Identifier' ||
      callee.property.type !== 'Identifier' ||
      !receivers.has(callee.object.name)
    ) {
      return null;
    }
    if (MESSAGE_METHODS.has(callee.property.name)) {
      return { isPromise: false };
    }
    return callee.property.name === 'promise' ? { isPromise: true } : null;
  };

  const recordExpression = (expression: Expression): void => {
    for (const literal of renderedLiterals(expression)) {
      const text = (staticText(literal) ?? '').replace(/\s+/g, ' ').trim();
      if (HAS_LETTER.test(text)) {
        sites.push({ line: lineAt(source, literal.start), text });
      }
      if (literal.type === 'TemplateLiteral') {
        literal.expressions.forEach((inner) => recordExpression(inner));
      }
    }
  };

  const recordOptions = (options: Argument | undefined, copyProperties: ReadonlySet<string>): void => {
    if (options?.type !== 'ObjectExpression') {
      return;
    }
    for (const property of options.properties) {
      const named = namedProperty(property);
      if (!named) {
        continue;
      }
      if (copyProperties.has(named.name)) {
        recordExpression(named.value);
      } else if (BUTTON_PROPERTIES.has(named.name) && named.value.type === 'ObjectExpression') {
        for (const inner of named.value.properties) {
          const label = namedProperty(inner);
          if (label?.name === 'label') {
            recordExpression(label.value);
          }
        }
      }
    }
  };

  const recordToastCall = ({ arguments: [first, second] }: CallExpression, { isPromise }: ToastCall): void => {
    if (first?.type === 'ObjectExpression') {
      recordOptions(first, COPY_PROPERTIES);
      return;
    }
    if (first && first.type !== 'SpreadElement' && !isPromise) {
      recordExpression(first);
    }
    recordOptions(second, isPromise ? PROMISE_COPY_PROPERTIES : COPY_PROPERTIES);
  };

  new Visitor({
    CallExpression(call) {
      const toast = toastCall(call.callee);
      if (toast) {
        recordToastCall(call, toast);
      }
    },
  }).visit(program);

  return sites.sort((a, b) => a.line - b.line);
}
