/**
 * next-intl 忽略的翻译选项静态扫描：找出 `t(key, { defaultValue })` / `t(key, { defaultMessage })` 这类调用。
 *
 * next-intl 没有这两个选项（那是 i18next / react-intl 的写法）：键缺失时它返回 `命名空间.key` 路径，
 * 不读兜底文案。写上它们只会制造「缺键也不会露馅」的错觉，兜底串从不显示，却一直留在代码里，
 * 还会让测试用本地 mock 伪造出用户从未见过的文案。需要兜底时用 `lib/i18n/translateOrRaw`。
 *
 * 判定按翻译器变量的命名（`t`、`tChat`、`tm`、`thinkT`），不依赖类型信息：翻译器既可能来自
 * `useTranslations`，也可能作为参数传入组件与纯函数，命名是两种来源共有的特征。
 */
import ts from 'typescript';

export type IgnoredIntlOptionName = 'defaultValue' | 'defaultMessage';

export interface IgnoredIntlOption {
  /** 选项所在行（从 1 起）。 */
  line: number;
  /** 调用的翻译器变量名，如 `t`、`tChat`。 */
  callee: string;
  option: IgnoredIntlOptionName;
}

const IGNORED_OPTIONS: ReadonlySet<string> = new Set<IgnoredIntlOptionName>(['defaultValue', 'defaultMessage']);

/** `t`、`tm`、`tChat`（小写 t 加大驼峰尾巴）或 `thinkT`（`…T` 后缀）；`toast`、`type`、`test` 不命中。 */
const TRANSLATOR_NAME = /^(?:t|tm|t[A-Z]\w*|\w+T)$/;

/** `t(...)` 取标识符本身，`t.rich(...)` / `t.markup(...)` 取点号前的翻译器。 */
function translatorName(callee: ts.Expression): string | null {
  if (ts.isIdentifier(callee)) {
    return callee.text;
  }
  if (ts.isPropertyAccessExpression(callee) && ts.isIdentifier(callee.expression)) {
    return callee.expression.text;
  }
  return null;
}

function ignoredOptionName(property: ts.ObjectLiteralElementLike): IgnoredIntlOptionName | null {
  if (!ts.isPropertyAssignment(property) && !ts.isShorthandPropertyAssignment(property)) {
    return null;
  }
  const { name } = property;
  if ((ts.isIdentifier(name) || ts.isStringLiteral(name)) && IGNORED_OPTIONS.has(name.text)) {
    return name.text as IgnoredIntlOptionName;
  }
  return null;
}

/** 返回源码里全部被 next-intl 忽略的翻译选项，按出现顺序。 */
export function findIgnoredIntlOptions(source: string, fileName: string): IgnoredIntlOption[] {
  const scriptKind = fileName.endsWith('x') ? ts.ScriptKind.TSX : ts.ScriptKind.TS;
  const file = ts.createSourceFile(fileName, source, ts.ScriptTarget.Latest, true, scriptKind);
  const found: IgnoredIntlOption[] = [];

  const visit = (node: ts.Node): void => {
    if (ts.isCallExpression(node)) {
      const callee = translatorName(node.expression);
      if (callee !== null && TRANSLATOR_NAME.test(callee)) {
        for (const argument of node.arguments) {
          if (!ts.isObjectLiteralExpression(argument)) {
            continue;
          }
          for (const property of argument.properties) {
            const option = ignoredOptionName(property);
            if (option !== null) {
              found.push({
                line: file.getLineAndCharacterOfPosition(property.getStart(file)).line + 1,
                callee,
                option,
              });
            }
          }
        }
      }
    }
    ts.forEachChild(node, visit);
  };
  visit(file);
  return found;
}
