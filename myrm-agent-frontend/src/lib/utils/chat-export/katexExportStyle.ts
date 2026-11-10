/**
 * [INPUT] `document.styleSheets` (the KaTeX stylesheet that this module's own CSS import puts on the page); `fetch` (the
 *         woff2 files that stylesheet names).
 * [OUTPUT] getKatexExportStyle.
 * [POS] The KaTeX CSS an exported document carries, so its formulas typeset when the file is opened outside the app.
 *       The import below is what guarantees the stylesheet is on the page: it loads together with this module, whichever
 *       route the export starts from, while the stylesheets of the chat components load only with their own routes.
 */
import 'katex/dist/katex.min.css';

/** The woff2 source of a `@font-face` rule: the smallest of the three KaTeX ships, and every browser that opens an export reads it. */
const WOFF2_SOURCE = /url\(\s*["']?([^"')]+)["']?\s*\)\s*format\(\s*["']woff2["']\s*\)/;

interface CollectedStyle {
  css: string;
  /** False when some part is missing, so the next export tries again instead of reusing a partial result. */
  complete: boolean;
}

let cachedStyle: Promise<string> | null = null;

function toBase64(bytes: Uint8Array): string {
  let binary = '';
  const chunk = 0x8000;
  for (let i = 0; i < bytes.length; i += chunk) {
    binary += String.fromCharCode(...bytes.subarray(i, i + chunk));
  }
  return btoa(binary);
}

/** The KaTeX rules of every stylesheet this page can read. */
function readKatexRules(): { styleRules: string[]; fontRules: { rule: CSSFontFaceRule; base: string }[] } {
  const styleRules: string[] = [];
  const fontRules: { rule: CSSFontFaceRule; base: string }[] = [];
  for (const sheet of Array.from(document.styleSheets)) {
    let rules: CSSRuleList;
    try {
      rules = sheet.cssRules;
    } catch {
      // A stylesheet served from another origin cannot be read.
      continue;
    }
    for (const rule of Array.from(rules)) {
      if (rule instanceof CSSFontFaceRule && rule.style.getPropertyValue('font-family').includes('KaTeX_')) {
        fontRules.push({ rule, base: sheet.href ?? document.baseURI });
      } else if (rule instanceof CSSStyleRule && rule.selectorText.includes('.katex')) {
        styleRules.push(rule.cssText);
      }
    }
  }
  return { styleRules, fontRules };
}

/** The rule with its font file embedded, or null when the file cannot be fetched (that font then falls back to a system one). */
async function embedFont(rule: CSSFontFaceRule, base: string): Promise<string | null> {
  const source = WOFF2_SOURCE.exec(rule.style.getPropertyValue('src'));
  if (!source) {
    return null;
  }
  try {
    const response = await fetch(new URL(source[1], base));
    if (!response.ok) {
      return null;
    }
    const dataUri = `data:font/woff2;base64,${toBase64(new Uint8Array(await response.arrayBuffer()))}`;
    const declarations = Array.from(rule.style, (name) =>
      name === 'src' ? `src:url(${dataUri}) format("woff2")` : `${name}:${rule.style.getPropertyValue(name)}`,
    );
    return `@font-face{${declarations.join(';')}}`;
  } catch {
    return null;
  }
}

async function collectKatexStyle(): Promise<CollectedStyle> {
  if (typeof document === 'undefined') {
    return { css: '', complete: false };
  }
  const { styleRules, fontRules } = readKatexRules();
  const fonts = await Promise.all(fontRules.map(({ rule, base }) => embedFont(rule, base)));
  const embedded = fonts.filter((font): font is string => font !== null);
  const complete = styleRules.length > 0 && fontRules.length > 0 && embedded.length === fontRules.length;
  if (!complete) {
    console.warn(
      `[chatExport] KaTeX styles are incomplete (${styleRules.length} rules, ${embedded.length} of ${fontRules.length} fonts embedded); formulas fall back to system fonts`,
    );
  }
  return { css: [...embedded, ...styleRules].join('\n'), complete };
}

/**
 * The KaTeX stylesheet for an exported document: its rules, and its `@font-face` rules with the woff2 files embedded
 * as data URIs. An empty string when the page has no readable KaTeX stylesheet; a font that cannot be fetched is left
 * out of the result. Only a complete result is kept for later exports.
 */
export function getKatexExportStyle(): Promise<string> {
  if (!cachedStyle) {
    const pending: Promise<string> = collectKatexStyle().then(({ css, complete }) => {
      if (!complete && cachedStyle === pending) {
        cachedStyle = null;
      }
      return css;
    });
    cachedStyle = pending;
  }
  return cachedStyle;
}
