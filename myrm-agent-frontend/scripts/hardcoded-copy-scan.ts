/**
 * 硬编码文案静态扫描：找出 TSX 里绕过 i18n 的用户可见字面量。
 *
 * 为什么需要：写死的文案不会让类型检查、单测或 jsx-a11y 失败，却会让其余语言的用户看到中文或英文原文；
 * 而 `verify-i18n` 只校验 locales JSON 内部一致，看不到 TSX 里没有进入 locales 的字面量。
 *
 * 扫描对象（TypeScript AST，不是正则）：
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
import ts from 'typescript';

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

/** 字符串字面量、无替换模板，以及静态片段拼接的模板（占位符处以空格隔开，避免把相邻片段误拼成单词）。 */
function staticText(node: ts.Node): string | null {
  if (ts.isStringLiteral(node) || ts.isNoSubstitutionTemplateLiteral(node)) {
    return node.text;
  }
  if (ts.isTemplateExpression(node)) {
    return [node.head.text, ...node.templateSpans.map((span) => span.literal.text)].join(' ');
  }
  return null;
}

/** 表达式里会被直接渲染的字符串分支：三元的两支、`&&` 右侧、`||` / `??` 两侧。 */
function renderedLiterals(expression: ts.Expression): ts.Node[] {
  if (staticText(expression) !== null) {
    return [expression];
  }
  if (ts.isParenthesizedExpression(expression)) {
    return renderedLiterals(expression.expression);
  }
  if (ts.isConditionalExpression(expression)) {
    return [...renderedLiterals(expression.whenTrue), ...renderedLiterals(expression.whenFalse)];
  }
  if (ts.isBinaryExpression(expression)) {
    const operator = expression.operatorToken.kind;
    if (operator === ts.SyntaxKind.AmpersandAmpersandToken) {
      return renderedLiterals(expression.right);
    }
    if (operator === ts.SyntaxKind.BarBarToken || operator === ts.SyntaxKind.QuestionQuestionToken) {
      return [...renderedLiterals(expression.left), ...renderedLiterals(expression.right)];
    }
  }
  return [];
}

function insideVerbatimElement(node: ts.Node): boolean {
  for (let current: ts.Node | undefined = node.parent; current; current = current.parent) {
    if (ts.isJsxElement(current) && VERBATIM_TAGS.has(current.openingElement.tagName.getText())) {
      return true;
    }
  }
  return false;
}

export function findHardcodedCopySites(source: string, fileName = 'source.tsx'): HardcodedCopySite[] {
  const file = ts.createSourceFile(fileName, source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
  const dualLanguageLocalized = LOCALIZE_CALL.test(source);
  const sites: HardcodedCopySite[] = [];

  const record = (node: ts.Node, kind: HardcodedCopyKind, raw: string): void => {
    const text = raw.replace(/\s+/g, ' ').trim();
    if (!text || !isCopy(text, dualLanguageLocalized)) {
      return;
    }
    const lead = ts.isJsxText(node) ? raw.length - raw.trimStart().length : 0;
    sites.push({ line: file.getLineAndCharacterOfPosition(node.getStart(file) + lead).line + 1, kind, text });
  };

  const recordExpression = (expression: ts.Expression, kind: HardcodedCopyKind): void => {
    for (const literal of renderedLiterals(expression)) {
      record(literal, kind, staticText(literal) ?? '');
    }
  };

  const visit = (node: ts.Node): void => {
    if (ts.isJsxText(node)) {
      if (!insideVerbatimElement(node)) {
        record(node, 'text', node.text);
      }
    } else if (
      ts.isJsxExpression(node) &&
      node.expression &&
      (ts.isJsxElement(node.parent) || ts.isJsxFragment(node.parent))
    ) {
      if (!insideVerbatimElement(node)) {
        recordExpression(node.expression, 'expression');
      }
    } else if (ts.isJsxAttribute(node) && node.initializer && COPY_ATTRIBUTE.test(node.name.getText(file))) {
      const { initializer } = node;
      if (ts.isStringLiteral(initializer)) {
        record(initializer, 'attribute', initializer.text);
      } else if (ts.isJsxExpression(initializer) && initializer.expression) {
        recordExpression(initializer.expression, 'attribute');
      }
    }
    ts.forEachChild(node, visit);
  };
  visit(file);

  return sites;
}
