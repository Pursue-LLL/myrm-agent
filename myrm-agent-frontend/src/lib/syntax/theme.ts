/**
 * The colours of syntax-highlighted code, one theme per appearance, shared by every syntax-highlighted surface.
 *
 * [INPUT]
 * - prism-react-renderer::themes (POS: the stock One Light and One Dark themes, whose colours are written as `hsl(...)`)
 *
 * [OUTPUT]
 * - SyntaxTheme: the theme type a highlighter takes
 * - syntaxThemeFor: the theme of the current appearance (`resolvedTheme` of next-themes)
 *
 * [POS]
 * One Light and One Dark with only the colours that fall under 4.5:1 (WCAG AA, the bar the theme engine's
 * `meetsContrast` applies) on a surface the product draws code on replaced by a darker or lighter shade of the same
 * hue; every other colour is the stock one. Stock One Light puts comments at 2.2:1, strings at 2.7:1 and numbers at
 * 3.5:1 on the code surface, and the diff row tints (`bg-green-500/10`, `bg-red-500/10`) lower that further. Consumers
 * take their theme from here instead of picking `themes.oneLight` or `themes.oneDark` themselves, which keeps one
 * colour table for the chat code block, the step panel, the diff viewer and the workspace file view. The surfaces and
 * the 4.5:1 bar are held by `__tests__/theme.test.ts`.
 */
import { themes } from 'prism-react-renderer';
import type { PrismTheme } from 'prism-react-renderer';

export type SyntaxTheme = PrismTheme;

/**
 * Stock colour -> readable colour, keyed by the exact string the stock theme writes. A key that stops matching lets the
 * stock colour through, which `__tests__/theme.test.ts` catches as a contrast failure.
 */
type ColorReplacements = Readonly<Record<string, string>>;

const LIGHT_COLOR_REPLACEMENTS: ColorReplacements = {
  'hsl(230, 4%, 64%)': '#686971', // comment
  'hsl(35, 99%, 36%)': '#985901', // number, boolean, constant, attribute name
  'hsl(5, 74%, 59%)': '#c12b1d', // property, tag, deleted
  'hsl(119, 34%, 47%)': '#3b763a', // string, selector, builtin, inserted
  'hsl(221, 87%, 60%)': '#185cef', // function, operator, variable
  'hsl(198, 99%, 37%)': '#0170a0', // url
};

const DARK_COLOR_REPLACEMENTS: ColorReplacements = {
  'hsl(220, 10%, 40%)': '#8b92a0', // comment
  'hsl(355, 65%, 65%)': '#e48189', // property, tag, deleted
};

function replaceColors(theme: PrismTheme, replacements: ColorReplacements): PrismTheme {
  return {
    plain: theme.plain,
    styles: theme.styles.map((entry) => {
      const replacement = entry.style.color === undefined ? undefined : replacements[entry.style.color];
      return replacement === undefined ? entry : { ...entry, style: { ...entry.style, color: replacement } };
    }),
  };
}

export const SYNTAX_THEME_LIGHT: SyntaxTheme = replaceColors(themes.oneLight, LIGHT_COLOR_REPLACEMENTS);
export const SYNTAX_THEME_DARK: SyntaxTheme = replaceColors(themes.oneDark, DARK_COLOR_REPLACEMENTS);

export function syntaxThemeFor(resolvedTheme: string | undefined): SyntaxTheme {
  return resolvedTheme === 'dark' ? SYNTAX_THEME_DARK : SYNTAX_THEME_LIGHT;
}
