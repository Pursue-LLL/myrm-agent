/**
 * 硬编码文案静态扫描：找出 TSX 里绕过 i18n 的用户可见字面量。
 *
 * 为什么需要：写死的文案不会让类型检查、单测或 jsx-a11y 失败，却会让其余语言的用户看到中文或英文原文；
 * 而 `verify-i18n` 只校验 locales JSON 内部一致，看不到 TSX 里没有进入 locales 的字面量。
 *
 * 扫描对象（oxc-parser 语法树，不是正则）：
 * - JSX 文本节点；
 * - JSX 子表达式里的字符串（`{'保存'}`、`{ok ? 'Done' : '完成'}`、`{busy && 'Saving…'}`，静态模板同理）；
 * - 承载展示文案的属性（`title` / `placeholder` / `aria-label` / `alt` / `label` / `description` 等）里的字符串。
 *
 * 判定为文案：含 CJK 字符，或含相邻两个英文单词（`Search files`）。单个英文单词（`ID`、`ms`、`Markdown`）
 * 无法区分文案与品牌 / 单位 / 协议名，宁可漏判也不误拦；这类合法的不翻译记号应提取为具名常量。
 *
 * 豁免：
 * - `<code>` / `<pre>` / `<kbd>` 等原样展示元素内的文本；
 * - 调用了 `localizeReactNode` 的文件里「中文 / English」双语字面量——该函数在渲染时只保留当前语言一侧。
 *
 * 不覆盖：写在对象 / 数组常量里再渲染的文案、`toast` / `Error` 消息、`.ts` 文件——这些位置的文案同样必须走 i18n，
 * 门禁看不到不代表合规。
 */
import { type Expression, type JSXElement, type JSXExpressionContainer, type Node, Visitor } from 'oxc-parser';

import { jsxNameText, lineAt, parseProgram } from './source-ast';

export type HardcodedCopyKind = 'text' | 'expression' | 'attribute';

export interface HardcodedCopySite {
  line: number;
  kind: HardcodedCopyKind;
  text: string;
}

const CJK = /[\p{Script=Han}\p{Script=Hiragana}\p{Script=Katakana}\p{Script=Hangul}]/u;
const ADJACENT_LATIN_WORDS = /[A-Za-z]{2,}\s+[A-Za-z]{2,}/;
/** 承载展示文案的属性名；`*Placeholder` / `*Label` 覆盖 `keyPlaceholder`、`nodeLabel` 这类组件自定义属性。 */
const COPY_ATTRIBUTE =
  /^(?:title|alt|placeholder|aria-label|aria-description|aria-roledescription|label|description|tooltip|helperText|emptyText|fallbackMessage|\w*Placeholder|\w*Label)$/;
/** 内容按字面原样展示、不应翻译的元素。 */
const VERBATIM_TAGS = new Set(['code', 'pre', 'kbd', 'samp', 'var', 'style', 'script']);
const DUAL_LANGUAGE_SEPARATOR = ' / ';
const LOCALIZE_CALL = /\blocalizeReactNode\s*\(/;

function isDualLanguage(text: string): boolean {
  const at = text.indexOf(DUAL_LANGUAGE_SEPARATOR);
  return at > 0 && text.slice(at + DUAL_LANGUAGE_SEPARATOR.length).trim().length > 0;
}

function isCopy(text: string, dualLanguageLocalized: boolean): boolean {
  if (CJK.test(text)) {
    return !(dualLanguageLocalized && isDualLanguage(text));
  }
  return ADJACENT_LATIN_WORDS.test(text);
}

/** 字符串字面量，以及静态片段拼接的模板（占位符处以空格隔开，避免把相邻片段误拼成单词）。 */
export function staticText(node: Node): string | null {
  if (node.type === 'Literal' && typeof node.value === 'string') {
    return node.value;
  }
  if (node.type === 'TemplateLiteral') {
    return node.quasis.map((quasi) => quasi.value.cooked ?? quasi.value.raw).join(' ');
  }
  return null;
}

/** 表达式里会被直接渲染的字符串分支：三元的两支、`&&` 右侧、`||` / `??` 两侧。 */
export function renderedLiterals(expression: Expression): Expression[] {
  if (staticText(expression) !== null) {
    return [expression];
  }
  switch (expression.type) {
    case 'ParenthesizedExpression':
      return renderedLiterals(expression.expression);
    case 'ConditionalExpression':
      return [...renderedLiterals(expression.consequent), ...renderedLiterals(expression.alternate)];
    case 'LogicalExpression':
      return expression.operator === '&&'
        ? renderedLiterals(expression.right)
        : [...renderedLiterals(expression.left), ...renderedLiterals(expression.right)];
    default:
      return [];
  }
}

function isVerbatimElement(element: JSXElement): boolean {
  return VERBATIM_TAGS.has(jsxNameText(element.openingElement.name));
}

export function findHardcodedCopySites(source: string, fileName = 'source.tsx'): HardcodedCopySite[] {
  const program = parseProgram(source, fileName);
  const dualLanguageLocalized = LOCALIZE_CALL.test(source);
  const sites: HardcodedCopySite[] = [];
  /** 属性值里的 `{…}` 由属性分支按属性名判定，不当作子表达式再扫一遍。 */
  const attributeValues = new Set<JSXExpressionContainer>();
  let verbatimDepth = 0;

  const record = (node: Node, kind: HardcodedCopyKind, raw: string): void => {
    const text = raw.replace(/\s+/g, ' ').trim();
    if (!text || !isCopy(text, dualLanguageLocalized)) {
      return;
    }
    // JSX 文本节点从前导空白起算，行号要落在第一个可见字符上。
    const lead = node.type === 'JSXText' ? raw.length - raw.trimStart().length : 0;
    sites.push({ line: lineAt(source, node.start + lead), kind, text });
  };

  const recordExpression = (expression: Expression, kind: HardcodedCopyKind): void => {
    for (const literal of renderedLiterals(expression)) {
      record(literal, kind, staticText(literal) ?? '');
    }
  };

  new Visitor({
    JSXElement(element) {
      if (isVerbatimElement(element)) {
        verbatimDepth += 1;
      }
    },
    'JSXElement:exit'(element) {
      if (isVerbatimElement(element)) {
        verbatimDepth -= 1;
      }
    },
    JSXText(text) {
      if (verbatimDepth === 0) {
        // 取源码原文：HTML 实体不解码，与肉眼所见一致。
        record(text, 'text', text.raw ?? text.value);
      }
    },
    JSXExpressionContainer(container) {
      if (
        verbatimDepth === 0 &&
        !attributeValues.has(container) &&
        container.expression.type !== 'JSXEmptyExpression'
      ) {
        recordExpression(container.expression, 'expression');
      }
    },
    JSXAttribute({ name, value }) {
      if (value?.type === 'JSXExpressionContainer') {
        attributeValues.add(value);
      }
      if (!value || !COPY_ATTRIBUTE.test(jsxNameText(name))) {
        return;
      }
      if (value.type === 'Literal') {
        record(value, 'attribute', value.value);
      } else if (value.type === 'JSXExpressionContainer' && value.expression.type !== 'JSXEmptyExpression') {
        recordExpression(value.expression, 'attribute');
      }
    },
  }).visit(program);

  return sites;
}
