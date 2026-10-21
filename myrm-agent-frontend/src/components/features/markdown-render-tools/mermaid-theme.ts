/**
 * [INPUT] CSS custom properties (--primary, --foreground, etc.) from document.documentElement
 * [OUTPUT] buildMermaidConfig(), sanitizeMermaidSvg(), buildMermaidThemeVariables()
 * [POS] Mermaid theme customization and SVG DOM XSS sanitizer SSOT
 */

export const MERMAID_FONT_FAMILY =
  'ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, "Noto Sans", sans-serif';

export interface MermaidChartProps {
  chart: string;
  id?: string;
}

export interface LegendItem {
  className: string;
  label: string;
  color?: string;
}

function getCssVar(name: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

function buildMermaidThemeVariables(isDark: boolean) {
  const primary = getCssVar('--primary') || (isDark ? '#2993e9' : '#588e95');
  const foreground = getCssVar('--foreground') || (isDark ? '#fbfbf8' : '#0a0a0a');
  const background = getCssVar('--background') || (isDark ? '#0a0a0a' : '#fdfdfb');
  const secondary = getCssVar('--secondary') || (isDark ? '#111111' : '#f6f6f1');
  const border = getCssVar('--border') || (isDark ? '#1c1c1c' : '#f0f0ec');
  const muted = getCssVar('--muted-foreground') || (isDark ? '#f2f2ed' : '#1c1c1c');

  return {
    darkMode: isDark,
    primaryColor: secondary,
    primaryTextColor: foreground,
    primaryBorderColor: primary,
    secondaryColor: isDark ? '#1a1a2e' : '#e8f4f5',
    secondaryTextColor: foreground,
    secondaryBorderColor: border,
    tertiaryColor: isDark ? '#0d1117' : '#f0f9fa',
    tertiaryTextColor: muted,
    tertiaryBorderColor: border,
    background,
    textColor: foreground,
    lineColor: primary,
    fontFamily: MERMAID_FONT_FAMILY,
    fontSize: '14px',
    noteBkgColor: isDark ? '#1a1a2e' : '#fff9e6',
    noteTextColor: foreground,
    noteBorderColor: primary,
  };
}

export function buildMermaidConfig(isDark: boolean) {
  return {
    startOnLoad: false,
    theme: 'base' as const,
    securityLevel: 'strict' as const,
    htmlLabels: false,
    fontFamily: MERMAID_FONT_FAMILY,
    fontSize: 14,
    themeVariables: buildMermaidThemeVariables(isDark),
  };
}

/**
 * 严格净化 Mermaid 渲染出的 SVG 字符串，彻底防御 XSS 与外来脚本执行。
 *
 * 1. 拦截并移除 <script>、<foreignObject>、<iframe>、<object>、<embed>、<link> 等危险标签；
 * 2. 移除所有内联事件处理器属性（如 onload, onclick, onerror，无论大小写如 oNload）；
 * 3. 移除或中立化 href、xlink:href 属性，防止 javascript: 或未授权跨站跳转；
 * 4. 必须保证根节点为合法且唯一的 <svg>，否则返回空字符串回退为安全状态。
 */
export function sanitizeMermaidSvg(rawSvg: string): string {
  if (!rawSvg || typeof rawSvg !== 'string') {
    return '';
  }

  const trimmed = rawSvg.trim();
  if (!trimmed.toLowerCase().startsWith('<svg') || typeof DOMParser === 'undefined') {
    // 基础正则防呆 fallback（如 SSR / 非浏览器环境）
    return sanitizeMermaidSvgFallback(trimmed);
  }

  try {
    const parser = new DOMParser();
    const doc = parser.parseFromString(trimmed, 'image/svg+xml');

    // 检查 XML 解析错误
    const parserError = doc.querySelector('parsererror');
    if (parserError) {
      return '';
    }

    const svgElement = doc.documentElement;
    if (!svgElement || svgElement.nodeName.toLowerCase() !== 'svg') {
      return '';
    }

    // 危险标签黑名单（SVG XML 模式下大小写敏感，兼容 foreignobject 与 foreignObject）
    const dangerousTags = [
      'script',
      'foreignobject',
      'foreignObject',
      'iframe',
      'object',
      'embed',
      'link',
      'meta',
      'base',
    ];

    for (const tag of dangerousTags) {
      const elements = Array.from(svgElement.getElementsByTagName(tag));
      for (const el of elements) {
        el.parentNode?.removeChild(el);
      }
    }

    // 递归清洗所有节点的属性：剥离 on* 事件处理器与 href 注入
    const allElements = [svgElement, ...Array.from(svgElement.getElementsByTagName('*'))];
    for (const el of allElements) {
      const attributes = Array.from(el.attributes);
      for (const attr of attributes) {
        const attrName = attr.name.toLowerCase();
        const attrValue = attr.value.trim().toLowerCase();

        // 剥离任何 on* 事件处理器（如 onload, onclick, onmouseover 等）
        if (attrName.startsWith('on') || attrName.startsWith('@') || attrName.startsWith('v-on:')) {
          el.removeAttribute(attr.name);
          continue;
        }

        // 剥离或拦截 href / xlink:href / src 属性中的 javascript: 伪协议与危险链接
        if (attrName === 'href' || attrName.endsWith(':href') || attrName === 'src') {
          if (
            attrValue.startsWith('javascript:') ||
            attrValue.startsWith('data:text/html') ||
            attrValue.startsWith('vbscript:')
          ) {
            el.removeAttribute(attr.name);
          } else {
            // 在 strict 安全等级下剥离图节点点击外部链接跳转
            el.removeAttribute(attr.name);
          }
        }
      }
    }

    const serializer = new XMLSerializer();
    return serializer.serializeToString(svgElement);
  } catch {
    return '';
  }
}

/**
 * 无 DOM 运行环境下的纯正则降级清洗器
 */
function sanitizeMermaidSvgFallback(svg: string): string {
  if (!svg.toLowerCase().startsWith('<svg')) {
    return '';
  }
  let sanitized = svg;
  // 移除 script 标签及内容
  sanitized = sanitized.replace(/<script\b[^<]*(?:(?!<\/script>)<[^<]*)*<\/script>/gi, '');
  // 移除 foreignObject 标签及内容
  sanitized = sanitized.replace(/<foreignobject\b[^<]*(?:(?!<\/foreignobject>)<[^<]*)*<\/foreignobject>/gi, '');
  // 移除 on* 事件处理器
  sanitized = sanitized.replace(/\s+on[a-z]+\s*=\s*(?:'[^']*'|"[^"]*"|[^\s>]+)/gi, '');
  // 移除 href 伪协议
  sanitized = sanitized.replace(/\s+(?:xlink:)?href\s*=\s*(?:'[^']*'|"[^"]*"|[^\s>]+)/gi, '');
  return sanitized;
}
