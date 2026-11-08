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
import { type Expression, type ObjectPropertyKind, Visitor } from 'oxc-parser';

import { lineAt, parseProgram } from './source-ast';

export type IgnoredIntlOptionName = 'defaultValue' | 'defaultMessage';

export interface IgnoredIntlOption {
  /** 选项所在行（从 1 起）。 */
  line: number;
  /** 调用的翻译器变量名，如 `t`、`tChat`。 */
  callee: string;
  option: IgnoredIntlOptionName;
}

/** `t`、`tm`、`tChat`（小写 t 加大驼峰尾巴）或 `thinkT`（`…T` 后缀）；`toast`、`type`、`test` 不命中。 */
const TRANSLATOR_NAME = /^(?:t|tm|t[A-Z]\w*|\w+T)$/;

/** `t(...)` 取标识符本身，`t.rich(...)` / `t.markup(...)` 取点号前的翻译器。 */
function translatorName(callee: Expression): string | null {
  if (callee.type === 'Identifier') {
    return callee.name;
  }
  if (callee.type === 'MemberExpression' && !callee.computed && callee.object.type === 'Identifier') {
    return callee.object.name;
  }
  return null;
}

function ignoredOptionName(property: ObjectPropertyKind): IgnoredIntlOptionName | null {
  if (property.type !== 'Property' || property.kind !== 'init' || property.method || property.computed) {
    return null;
  }
  const { key } = property;
  const name = key.type === 'Identifier' ? key.name : key.type === 'Literal' ? key.value : null;
  return name === 'defaultValue' || name === 'defaultMessage' ? name : null;
}

/** 返回源码里全部被 next-intl 忽略的翻译选项，按出现顺序。 */
export function findIgnoredIntlOptions(source: string, fileName: string): IgnoredIntlOption[] {
  const found: IgnoredIntlOption[] = [];

  new Visitor({
    CallExpression(call) {
      const callee = translatorName(call.callee);
      if (callee === null || !TRANSLATOR_NAME.test(callee)) {
        return;
      }
      for (const argument of call.arguments) {
        if (argument.type !== 'ObjectExpression') {
          continue;
        }
        for (const property of argument.properties) {
          const option = ignoredOptionName(property);
          if (option !== null) {
            found.push({ line: lineAt(source, property.start), callee, option });
          }
        }
      }
    },
  }).visit(parseProgram(source, fileName));

  return found;
}
