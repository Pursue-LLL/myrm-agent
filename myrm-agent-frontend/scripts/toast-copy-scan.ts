/**
 * Toast 文案静态扫描：找出 `toast` 调用里写死的用户可见文案。
 *
 * 为什么需要：`hardcoded-copy-scan.ts` 只看 TSX 里的 JSX，toast 消息写在事件处理 / store / 工具函数里，
 * 同样会让其余语言的用户看到中文或英文原文，且类型检查、单测都发现不了。
 *
 * 扫描对象（TypeScript AST，`.ts` 与 `.tsx` 都扫）：
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
import ts from 'typescript';

import { renderedLiterals, staticText } from './hardcoded-copy-scan';

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

function propertyName(property: ts.ObjectLiteralElementLike): string | null {
  if (!ts.isPropertyAssignment(property)) {
    return null;
  }
  const { name } = property;
  return ts.isIdentifier(name) || ts.isStringLiteral(name) ? name.text : null;
}

/** 本文件里指向 toast 的名字：`toast` 本身、`import { toast as alias }` 的别名，以及转发对象。 */
function toastReceivers(file: ts.SourceFile): Set<string> {
  const receivers = new Set(['toast', ...FORWARDING_RECEIVERS]);
  for (const statement of file.statements) {
    const bindings = ts.isImportDeclaration(statement) ? statement.importClause?.namedBindings : undefined;
    if (!bindings || !ts.isNamedImports(bindings)) {
      continue;
    }
    for (const specifier of bindings.elements) {
      if ((specifier.propertyName ?? specifier.name).text === 'toast') {
        receivers.add(specifier.name.text);
      }
    }
  }
  return receivers;
}

export function findToastCopySites(source: string, fileName = 'source.tsx'): ToastCopySite[] {
  if (!MENTIONS_TOAST.test(source)) {
    return [];
  }
  const scriptKind = fileName.endsWith('.tsx') ? ts.ScriptKind.TSX : ts.ScriptKind.TS;
  const file = ts.createSourceFile(fileName, source, ts.ScriptTarget.Latest, true, scriptKind);
  const receivers = toastReceivers(file);
  const sites: ToastCopySite[] = [];

  const toastCall = (callee: ts.Expression): ToastCall | null => {
    if (ts.isIdentifier(callee)) {
      return receivers.has(callee.text) ? { isPromise: false } : null;
    }
    if (!ts.isPropertyAccessExpression(callee) || !ts.isIdentifier(callee.expression)) {
      return null;
    }
    if (!receivers.has(callee.expression.text)) {
      return null;
    }
    if (MESSAGE_METHODS.has(callee.name.text)) {
      return { isPromise: false };
    }
    return callee.name.text === 'promise' ? { isPromise: true } : null;
  };

  const recordExpression = (expression: ts.Expression): void => {
    for (const literal of renderedLiterals(expression)) {
      const text = (staticText(literal) ?? '').replace(/\s+/g, ' ').trim();
      if (HAS_LETTER.test(text)) {
        sites.push({ line: file.getLineAndCharacterOfPosition(literal.getStart(file)).line + 1, text });
      }
      if (ts.isTemplateExpression(literal)) {
        literal.templateSpans.forEach((span) => recordExpression(span.expression));
      }
    }
  };

  const recordOptions = (options: ts.Expression | undefined, copyProperties: ReadonlySet<string>): void => {
    if (!options || !ts.isObjectLiteralExpression(options)) {
      return;
    }
    for (const property of options.properties) {
      const name = propertyName(property);
      if (name === null || !ts.isPropertyAssignment(property)) {
        continue;
      }
      if (copyProperties.has(name)) {
        recordExpression(property.initializer);
      } else if (BUTTON_PROPERTIES.has(name) && ts.isObjectLiteralExpression(property.initializer)) {
        for (const inner of property.initializer.properties) {
          if (propertyName(inner) === 'label' && ts.isPropertyAssignment(inner)) {
            recordExpression(inner.initializer);
          }
        }
      }
    }
  };

  const recordToastCall = (call: ts.CallExpression, { isPromise }: ToastCall): void => {
    const [first, second] = call.arguments;
    if (first && ts.isObjectLiteralExpression(first)) {
      recordOptions(first, COPY_PROPERTIES);
      return;
    }
    if (first && !isPromise) {
      recordExpression(first);
    }
    recordOptions(second, isPromise ? PROMISE_COPY_PROPERTIES : COPY_PROPERTIES);
  };

  const visit = (node: ts.Node): void => {
    if (ts.isCallExpression(node)) {
      const call = toastCall(node.expression);
      if (call) {
        recordToastCall(node, call);
      }
    }
    ts.forEachChild(node, visit);
  };
  visit(file);

  return sites.sort((a, b) => a.line - b.line);
}
