/**
 * 键盘焦点可见性静态扫描：找出 className 里写了 `outline-none` 却没有任何可见焦点替代样式的元素。
 *
 * 为什么需要：全局 `src/app/focus-ring.css` 位于 `@layer base`，会被无层级的 Tailwind
 * `outline-none` 工具类覆盖；而 jsx-a11y 与 axe 都无法判断“聚焦后是否有可见变化”，
 * 于是键盘用户 Tab 到这类元素时看不到焦点（见 BaseModelSelector / model-picker-popover 的修复）。
 *
 * 判定单元是完整的 className 属性值（含 cn() 多参数、三元、模板字符串跨行），而不是单行文本——
 * 替代样式常写在同一个 cn() 的另一行参数里，按行匹配会大量误报。
 */

/** 聚焦时可见的替代样式（ring / border / shadow / bg / underline / text / 非 none 的 outline）。 */
const VISIBLE_FOCUS_STYLE =
  /\bfocus(?:-visible|-within)?:(?:ring|border|shadow|bg|underline|text|outline-(?!none|hidden))|data-\[selected(?:=true)?\]:bg/;
const OUTLINE_NONE = /(?<![\w-])outline-none(?![\w-])/;
const CLASS_ATTRIBUTE = /\b\w*[cC]lassName\s*=\s*/g;
/**
 * 无需自带焦点环的元素：文本输入由外层容器承担焦点反馈、媒体由浏览器原生控件承担、
 * Radix `*.Content` 浮层容器由库在打开时程序化聚焦。
 */
const EXEMPT_TAG = /^(?:audio|video)$|input$|select$|textarea|content$/i;
/** tabIndex={-1} 的元素无法被 Tab 到达，只会被程序化聚焦，不需要键盘焦点环。 */
const NOT_TAB_REACHABLE = /\btabIndex=\{-1\}/;

export interface InvisibleFocusSite {
  line: number;
  tag: string;
}

function skipQuoted(source: string, start: number): number {
  const quote = source[start];
  let i = start + 1;
  while (i < source.length && source[i] !== quote) {
    if (source[i] === '\\') {
      i += 1;
    } else if (quote === '`' && source[i] === '$' && source[i + 1] === '{') {
      i = skipBraces(source, i + 1);
      continue;
    }
    i += 1;
  }
  return i + 1;
}

function skipBraces(source: string, start: number): number {
  let depth = 0;
  let i = start;
  while (i < source.length) {
    const ch = source[i];
    if (ch === '"' || ch === "'" || ch === '`') {
      i = skipQuoted(source, i);
      continue;
    }
    if (ch === '{') {
      depth += 1;
    } else if (ch === '}') {
      depth -= 1;
      if (depth === 0) {
        return i + 1;
      }
    }
    i += 1;
  }
  return source.length;
}

function readAttributeValueEnd(source: string, start: number): number {
  const ch = source[start];
  if (ch === '"' || ch === "'") {
    return skipQuoted(source, start);
  }
  return ch === '{' ? skipBraces(source, start) : start;
}

function readOpeningTagEnd(source: string, open: number): number {
  let i = open + 1;
  while (i < source.length && source[i] !== '>') {
    const ch = source[i];
    if (ch === '{') {
      i = skipBraces(source, i);
    } else if (ch === '"' || ch === "'") {
      i = skipQuoted(source, i);
    } else {
      i += 1;
    }
  }
  return i;
}

export function findInvisibleFocusSites(source: string): InvisibleFocusSite[] {
  const sites: InvisibleFocusSite[] = [];
  for (const match of source.matchAll(CLASS_ATTRIBUTE)) {
    const valueStart = match.index + match[0].length;
    const value = source.slice(valueStart, readAttributeValueEnd(source, valueStart));
    if (!OUTLINE_NONE.test(value) || VISIBLE_FOCUS_STYLE.test(value)) {
      continue;
    }
    const open = source.lastIndexOf('<', match.index);
    if (open < 0) {
      continue;
    }
    const tag = /^<([A-Za-z][\w.]*)/.exec(source.slice(open, open + 64))?.[1] ?? '';
    if (EXEMPT_TAG.test(tag) || NOT_TAB_REACHABLE.test(source.slice(open, readOpeningTagEnd(source, open)))) {
      continue;
    }
    const offset = valueStart + value.search(OUTLINE_NONE);
    sites.push({ line: source.slice(0, offset).split('\n').length, tag });
  }
  return sites;
}
