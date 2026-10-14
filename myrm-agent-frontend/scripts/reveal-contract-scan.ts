/**
 * 悬停揭示契约静态扫描：找出只靠鼠标悬停才显现的可交互元素。
 *
 * 为什么需要：`opacity-0 group-hover:opacity-100` 的控件只在指针悬停父级时可见——键盘用户 Tab 到它时它仍是
 * 透明的，触屏设备又没有悬停，控件等于不存在，而 jsx-a11y 与单测都看不到。契约要求揭示同时有键盘路径
 * （`group-focus-within` / `focus-within` / `focus-visible` / `focus` 之一的 `:opacity-100`）与触屏路径
 * （`pointer-coarse:opacity-100`）；共享常量 `REVEAL_ON_HOVER`（`src/lib/utils/a11y.ts`）同时提供两者。
 *
 * 判定单元是 JSX 元素的 `className` 属性值（含 `cn()` 多参数、三元、模板字符串）。元素本身或它的任一后代
 * 是可交互元素时才算违规：箭头、提示文字这类纯装饰的悬停效果不受约束。
 *
 * 盲区：只解析写在 `className` 属性里的类名，不解析先拼进变量再传入的类名；也不判断
 * `pointer-events-none` 等让可交互元素无法被点击的写法。
 */
import ts from 'typescript';

export type MissingRevealPath = 'keyboard' | 'touch';

export interface HoverOnlyRevealSite {
  line: number;
  tag: string;
  missing: MissingRevealPath[];
}

/** 无任何变体前缀的 `opacity-0`；`md:opacity-0`、`hover:opacity-0` 等带变体的写法不是常驻隐藏。 */
const HIDDEN_BY_DEFAULT = /(?<![\w:/-])opacity-0(?![\w-])/;
/** 由祖先悬停触发的揭示，支持具名 group（`group-hover/row:opacity-100`）。 */
const REVEALED_ON_ANCESTOR_HOVER = /(?<![\w:/-])group-hover(?:\/[\w-]+)?:opacity-100/;
const KEYBOARD_REVEAL = /(?<![\w:/-])(?:group-)?focus(?:-visible|-within)?(?:\/[\w-]+)?:opacity-100/;
const TOUCH_REVEAL = /(?<![\w:/-])pointer-coarse:opacity-100/;
const SHARED_REVEAL_CONSTANT = /\bREVEAL_ON_HOVER\b/;

const INTERACTIVE_HTML_TAGS = new Set(['button', 'a', 'input', 'select', 'textarea', 'summary']);
/**
 * 自定义封装（取点号后的最后一段）：`Button`、`IconButton`、`DropdownMenuTrigger`、`Primitive.Trigger` 等。
 * 链接只认 `Link` / `NavLink`，不认 `ExternalLink` 这类以 Link 结尾的图标组件。
 */
const INTERACTIVE_COMPONENT_TAG = /^(?:Link|NavLink|\w*Button|\w*Trigger|\w*MenuItem|\w*Checkbox|\w*Switch|\w*Toggle)$/;
const INTERACTIVE_HANDLER = /^on(?:Click|DoubleClick|KeyDown|KeyUp|PointerDown|MouseDown|Change)$/;
const INTERACTIVE_ROLES = new Set(['button', 'link', 'menuitem', 'switch', 'checkbox', 'tab', 'option']);

type JsxTagNode = ts.JsxOpeningElement | ts.JsxSelfClosingElement;

function isJsxTag(node: ts.Node): node is JsxTagNode {
  return ts.isJsxOpeningElement(node) || ts.isJsxSelfClosingElement(node);
}

function attributeOf(tag: JsxTagNode, name: string): ts.JsxAttribute | undefined {
  return tag.attributes.properties.find(
    (property): property is ts.JsxAttribute => ts.isJsxAttribute(property) && property.name.getText() === name,
  );
}

function isInteractiveTag(tag: JsxTagNode, source: ts.SourceFile): boolean {
  const name = tag.tagName.getText(source);
  if (INTERACTIVE_HTML_TAGS.has(name) || INTERACTIVE_COMPONENT_TAG.test(name.slice(name.lastIndexOf('.') + 1))) {
    return true;
  }
  const role = attributeOf(tag, 'role')?.initializer;
  if (role && ts.isStringLiteral(role) && INTERACTIVE_ROLES.has(role.text)) {
    return true;
  }
  return tag.attributes.properties.some(
    (property) => ts.isJsxAttribute(property) && INTERACTIVE_HANDLER.test(property.name.getText(source)),
  );
}

/** 元素本身或其任一后代是可交互元素。 */
function containsInteractive(element: ts.Node, source: ts.SourceFile): boolean {
  let found = false;
  const visit = (node: ts.Node): void => {
    if (found) {
      return;
    }
    if (isJsxTag(node) && isInteractiveTag(node, source)) {
      found = true;
      return;
    }
    ts.forEachChild(node, visit);
  };
  visit(element);
  return found;
}

function missingPaths(className: string): MissingRevealPath[] {
  if (SHARED_REVEAL_CONSTANT.test(className)) {
    return [];
  }
  const missing: MissingRevealPath[] = [];
  if (!KEYBOARD_REVEAL.test(className)) {
    missing.push('keyboard');
  }
  if (!TOUCH_REVEAL.test(className)) {
    missing.push('touch');
  }
  return missing;
}

export function findHoverOnlyRevealSites(source: string): HoverOnlyRevealSite[] {
  const file = ts.createSourceFile('scan.tsx', source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
  const sites: HoverOnlyRevealSite[] = [];

  const visit = (node: ts.Node): void => {
    if (isJsxTag(node)) {
      const className = attributeOf(node, 'className')?.getText(file) ?? '';
      if (HIDDEN_BY_DEFAULT.test(className) && REVEALED_ON_ANCESTOR_HOVER.test(className)) {
        const missing = missingPaths(className);
        const element = ts.isJsxOpeningElement(node) ? node.parent : node;
        if (missing.length > 0 && containsInteractive(element, file)) {
          sites.push({
            line: file.getLineAndCharacterOfPosition(node.getStart(file)).line + 1,
            tag: node.tagName.getText(file),
            missing,
          });
        }
      }
    }
    ts.forEachChild(node, visit);
  };
  visit(file);
  return sites;
}
