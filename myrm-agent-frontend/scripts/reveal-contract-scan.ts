/**
 * 悬停揭示契约静态扫描：找出只靠鼠标悬停才显现的可交互元素。
 *
 * [INPUT]  source: string（TSX 源码字符串）
 * [OUTPUT] findHoverOnlyRevealSites(): HoverOnlyRevealSite[]
 * [POS]    无障碍门禁底层扫描器，兼容 Babel/TypeScript 7 AST
 */
import { parse } from '@babel/parser';

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

function getTagName(nameNode: any): string {
  if (!nameNode) return '';
  if (nameNode.type === 'JSXIdentifier') {
    return nameNode.name;
  }
  if (nameNode.type === 'JSXMemberExpression') {
    return `${getTagName(nameNode.object)}.${nameNode.property.name}`;
  }
  return '';
}

function getRawAttributeValue(attrNode: any, source: string): string {
  if (!attrNode || !attrNode.value) return '';
  const val = attrNode.value;
  if (val.type === 'StringLiteral') {
    return val.value;
  }
  if (val.type === 'JSXExpressionContainer' && val.start != null && val.end != null) {
    return source.slice(val.start, val.end);
  }
  return '';
}

function isInteractiveTag(opening: any, source: string): boolean {
  const name = getTagName(opening.name);
  const baseName = name.slice(name.lastIndexOf('.') + 1);
  if (INTERACTIVE_HTML_TAGS.has(name) || INTERACTIVE_COMPONENT_TAG.test(baseName)) {
    return true;
  }
  for (const attr of opening.attributes || []) {
    if (attr.type === 'JSXAttribute') {
      const attrName = attr.name?.name;
      if (attrName === 'role' && attr.value?.type === 'StringLiteral' && INTERACTIVE_ROLES.has(attr.value.value)) {
        return true;
      }
      if (typeof attrName === 'string' && INTERACTIVE_HANDLER.test(attrName)) {
        return true;
      }
    }
  }
  return false;
}

function containsInteractive(elementNode: any, source: string): boolean {
  let found = false;
  function walk(node: any) {
    if (found || !node || typeof node !== 'object') return;
    if (node.type === 'JSXElement') {
      if (isInteractiveTag(node.openingElement, source)) {
        found = true;
        return;
      }
    } else if (node.type === 'JSXOpeningElement') {
      if (isInteractiveTag(node, source)) {
        found = true;
        return;
      }
    }
    for (const key of Object.keys(node)) {
      if (key === 'parent' || key === 'tokens') continue;
      const child = node[key];
      if (Array.isArray(child)) {
        for (const c of child) walk(c);
      } else if (child && typeof child === 'object') {
        walk(child);
      }
    }
  }
  walk(elementNode);
  return found;
}

export function findHoverOnlyRevealSites(source: string): HoverOnlyRevealSite[] {
  let ast: any;
  try {
    ast = parse(source, {
      sourceType: 'module',
      plugins: ['jsx', 'typescript'],
      errorRecovery: true,
    });
  } catch {
    return [];
  }

  const sites: HoverOnlyRevealSite[] = [];

  function traverse(node: any, parent: any) {
    if (!node || typeof node !== 'object') return;

    if (node.type === 'JSXElement') {
      const opening = node.openingElement;
      let className = '';
      for (const attr of opening.attributes || []) {
        if (attr.type === 'JSXAttribute' && attr.name?.name === 'className') {
          className = getRawAttributeValue(attr, source);
          break;
        }
      }

      if (HIDDEN_BY_DEFAULT.test(className) && REVEALED_ON_ANCESTOR_HOVER.test(className)) {
        const missing = missingPaths(className);
        if (missing.length > 0 && containsInteractive(node, source)) {
          sites.push({
            line: opening.loc ? opening.loc.start.line : 1,
            tag: getTagName(opening.name),
            missing,
          });
        }
      }
    }

    for (const key of Object.keys(node)) {
      if (key === 'parent' || key === 'tokens') continue;
      const child = node[key];
      if (Array.isArray(child)) {
        for (const c of child) traverse(c, node);
      } else if (child && typeof child === 'object') {
        traverse(child, node);
      }
    }
  }

  traverse(ast, null);
  return sites;
}
