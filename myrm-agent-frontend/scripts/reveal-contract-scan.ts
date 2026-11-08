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
import { type JSXAttribute, type JSXOpeningElement, Visitor } from 'oxc-parser';

import { jsxNameText, lineAt, parseProgram } from './source-ast';

export type MissingRevealPath = 'keyboard' | 'touch';

export interface HoverOnlyRevealSite {
  line: number;
  tag: string;
  missing: MissingRevealPath[];
}

const HIDDEN_BY_DEFAULT = /(?<![\w:/-])opacity-0(?![\w-])/;
const REVEALED_ON_ANCESTOR_HOVER = /(?<![\w:/-])group-hover(?:\/[\w-]+)?:opacity-100/;
const KEYBOARD_REVEAL = /(?<![\w:/-])(?:group-)?focus(?:-visible|-within)?(?:\/[\w-]+)?:opacity-100/;
const TOUCH_REVEAL = /(?<![\w:/-])pointer-coarse:opacity-100/;
const SHARED_REVEAL_CONSTANT = /\bREVEAL_ON_HOVER\b/;

const INTERACTIVE_HTML_TAGS = new Set(['button', 'a', 'input', 'select', 'textarea', 'summary']);
const INTERACTIVE_COMPONENT_TAG = /^(?:Link|NavLink|\w*Button|\w*Trigger|\w*MenuItem|\w*Checkbox|\w*Switch|\w*Toggle)$/;
const INTERACTIVE_HANDLER = /^on(?:Click|DoubleClick|KeyDown|KeyUp|PointerDown|MouseDown|Change)$/;
const INTERACTIVE_ROLES = new Set(['button', 'link', 'menuitem', 'switch', 'checkbox', 'tab', 'option']);

function attributeOf(tag: JSXOpeningElement, name: string): JSXAttribute | undefined {
  for (const attribute of tag.attributes) {
    if (attribute.type === 'JSXAttribute' && jsxNameText(attribute.name) === name) {
      return attribute;
    }
  }
  return undefined;
}

function isInteractiveTag(tag: JSXOpeningElement): boolean {
  const name = jsxNameText(tag.name);
  if (INTERACTIVE_HTML_TAGS.has(name) || INTERACTIVE_COMPONENT_TAG.test(name.slice(name.lastIndexOf('.') + 1))) {
    return true;
  }
  const role = attributeOf(tag, 'role')?.value;
  if (role?.type === 'Literal' && INTERACTIVE_ROLES.has(role.value)) {
    return true;
  }
  return tag.attributes.some(
    (attribute) => attribute.type === 'JSXAttribute' && INTERACTIVE_HANDLER.test(jsxNameText(attribute.name)),
  );
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

/**
 * 一个 JSX 元素的判定状态。`interactive`（自身或任一后代可交互）要等子树遍历完才确定，
 * 所以元素先按文档顺序登记，遍历结束后再统一取出违规的。
 */
interface ElementState {
  interactive: boolean;
  /** 只有 className 满足「默认透明、悬停才揭示、缺键盘或触屏路径」时才有。 */
  site: HoverOnlyRevealSite | null;
}

function revealSite(source: string, tag: JSXOpeningElement): HoverOnlyRevealSite | null {
  const attribute = attributeOf(tag, 'className');
  const className = attribute ? source.slice(attribute.start, attribute.end) : '';
  if (!HIDDEN_BY_DEFAULT.test(className) || !REVEALED_ON_ANCESTOR_HOVER.test(className)) {
    return null;
  }
  const missing = missingPaths(className);
  return missing.length > 0 ? { line: lineAt(source, tag.start), tag: jsxNameText(tag.name), missing } : null;
}

export function findHoverOnlyRevealSites(source: string): HoverOnlyRevealSite[] {
  const elements: ElementState[] = [];
  const ancestors: ElementState[] = [];

  new Visitor({
    JSXElement({ openingElement }) {
      const element = { interactive: isInteractiveTag(openingElement), site: revealSite(source, openingElement) };
      elements.push(element);
      ancestors.push(element);
    },
    'JSXElement:exit'() {
      const element = ancestors.pop();
      const parent = ancestors.at(-1);
      if (element?.interactive && parent) {
        parent.interactive = true;
      }
    },
  }).visit(parseProgram(source, 'source.tsx'));

  return elements.flatMap(({ interactive, site }) => (interactive && site ? [site] : []));
}
