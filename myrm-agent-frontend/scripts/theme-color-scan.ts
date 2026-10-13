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
