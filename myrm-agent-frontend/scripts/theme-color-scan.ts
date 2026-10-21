/**
 * 主题色写法静态扫描：找出把主题变量包进 `hsl()` / `hsla()` / `rgb()` / `rgba()` 的写法。
 *
 * 为什么需要：主题变量存的是完整颜色（`globals.css` 的 `--primary: #6799a0`，`theme-engine` 运行时写入的
 * 同样是 `#rrggbb`），包进颜色函数后整条声明在计算时失效。浏览器不报错、控制台没有告警：SVG 描边变 `none`、
 * 填充变黑、`box-shadow` 整条消失，单测与 jsdom 都看不见，只有真实渲染才暴露。
 *
 * 正确写法：直接 `var(--primary)`；需要透明度时用 `color-mix(in srgb, var(--primary) 20%, transparent)`，
 * Tailwind 类里用 `shadow-primary/20`、`bg-primary/20` 这类透明度修饰符。
 *
 * 只拦“变量即整个颜色”的形态：`hsl(var(--x))`、`hsl(var(--x) / 0.2)`、`rgba(var(--x), 0.2)`。
 * 以下写法合法，不会被拦：`hsl(var(--hue) 58% 48%)`（变量只是色相通道）、`hsl(var(--x, 217 91% 60%))`
 * （带三元组回退）；`--widget-*` 由 `widget-theme-bridge` 在 iframe 内注入三元组，包装是合法的。
 */

/**
 * `<fn>(var(--name)` 之后紧跟 `)` / `/` / `, <alpha>)`，说明变量就是整个颜色；只返回 `<fn>(var(--name)` 这段。
 * 函数名前不能是字母或连字符（排除 `color-rgb(`），但允许 `_`：Tailwind 任意值里 `_` 就是空格（`8px_hsl(`）。
 */
const WRAPPED_THEME_VAR =
  /(?<![A-Za-z-])(?:hsla?|rgba?)\(\s*var\(\s*--(?!widget-)[\w-]+\s*\)(?=\s*(?:\)|\/|,\s*[\d.]+%?\s*\)))/g;

/**
 * 本规则的前提：主题变量存的是完整颜色（`#6799a0`、`oklch(...)` 等）。若某天换成 `210 40% 50%` 这样的通道三元组，
 * 包 `hsl()` 反而是对的，规则就会拦下合法写法——门禁用它校验 `--primary`，前提失效时直接报错而不是误拦。
 */
export function isCompleteColorValue(value: string): boolean {
  return /^(?:#[0-9a-f]{3,8}|(?:oklch|oklab|lch|lab|rgba?|hsla?|color)\()/i.test(value.trim());
}

export interface WrappedThemeColorSite {
  line: number;
  text: string;
}

export function findWrappedThemeColorSites(source: string): WrappedThemeColorSite[] {
  const sites: WrappedThemeColorSite[] = [];
  for (const match of source.matchAll(WRAPPED_THEME_VAR)) {
    const line = source.slice(0, match.index).split('\n').length;
    sites.push({ line, text: match[0] });
  }
  return sites;
}

/**
 * 语义色工具类（`text-warning`、`bg-success/10`、`to-error`）必须在 `globals.css` 里有对应的 `--color-*` 声明。
 * Tailwind 4 只为已声明的颜色生成工具类，未声明的类名不报错也不出样式：告警框没底色没描边，单测与 jsdom 看不见。
 *
 * 只盯这几个“像主题语义色、却最容易漏定义”的名字，避免把 `text-xs`、`bg-cover` 之类误判成颜色；
 * 前缀之前不能是字母 / 数字 / `_` / `-`，所以 `seek-to-error` 这种连字符词不会误中，而 `hover:bg-warning` 会命中。
 */
const SEMANTIC_COLOR_UTILITY =
  /(?<![\w-])(?:bg|text|border|ring|fill|stroke|from|via|to|outline|divide|shadow|decoration|accent|caret|placeholder)-((?:success|warning|info|danger|error)(?:-foreground)?)(?![\w-])/g;

export interface UndefinedSemanticColorSite {
  line: number;
  text: string;
  /** 缺失的主题颜色名，对应 `--color-<token>`。 */
  token: string;
}

/** 读出 `globals.css` 里声明过的 `--color-<name>`（Tailwind 据此生成颜色工具类）。 */
export function parseDeclaredColorTokens(globalsCss: string): Set<string> {
  return new Set(Array.from(globalsCss.matchAll(/--color-([\w-]+)\s*:/g), (match) => match[1]));
}

export function findUndefinedSemanticColorSites(
  source: string,
  declaredColorTokens: ReadonlySet<string>,
): UndefinedSemanticColorSite[] {
  const sites: UndefinedSemanticColorSite[] = [];
  for (const match of source.matchAll(SEMANTIC_COLOR_UTILITY)) {
    if (!declaredColorTokens.has(match[1])) {
      const line = source.slice(0, match.index).split('\n').length;
      sites.push({ line, text: match[0], token: match[1] });
    }
  }
  return sites;
}
