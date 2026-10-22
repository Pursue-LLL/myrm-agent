/**
 * [INPUT]
 * - wechatPreviewTypes: WechatThemeId, WechatThemeConfig, WechatBlockStyles, FontSizeScale
 *
 * [OUTPUT]
 * - WECHAT_THEMES, compileWechatInlineHtml, getWechatTheme
 *
 * [POS]
 * Theme definitions and inline CSS compiler for WeChat Official Account articles (Item 45 P0).
 * Strictly under 320 lines. Zero `any`.
 */

import type {
  FontSizeScale,
  WechatBlockStyles,
  WechatThemeConfig,
  WechatThemeId,
} from './wechatPreviewTypes';

const FONT_SCALES: Record<FontSizeScale, number> = {
  compact: 0.9,
  normal: 1.0,
  spacious: 1.1,
};

// 1. Classic Theme (微信原生活泼排版，品牌绿标)
const CLASSIC_STYLES: WechatBlockStyles = {
  h1: 'font-size: 22px; font-weight: 700; line-height: 1.4; margin: 28px 0 16px; color: #1a1a1a; text-align: center;',
  h2: 'font-size: 18px; font-weight: 700; line-height: 1.4; margin: 24px 0 12px; color: #1a1a1a; border-left: 4px solid #07c160; padding-left: 12px;',
  h3: 'font-size: 16px; font-weight: 600; line-height: 1.4; margin: 18px 0 8px; color: #2a2a2a;',
  p: 'margin: 14px 0; text-align: justify; line-height: 1.8; color: #3f3f3f; font-size: 15px;',
  blockquote: 'margin: 16px 0; padding: 12px 16px; background: #f6f6f6; border-left: 4px solid #07c160; color: #555555; border-radius: 4px; font-size: 14px;',
  pre: 'background: #282c34; color: #abb2bf; padding: 14px; border-radius: 8px; overflow-x: auto; margin: 16px 0; line-height: 1.5; font-size: 13px;',
  code: 'font-family: ui-monospace, SFMono-Regular, monospace; background: #f5f5f5; padding: 2px 6px; border-radius: 4px; font-size: 13px; color: #07c160;',
  table: 'width: 100%; border-collapse: collapse; margin: 16px 0; font-size: 13px;',
  th: 'border: 1px solid #e5e5e5; padding: 8px 12px; text-align: left; background: #f7f7f7; font-weight: 600; color: #1a1a1a;',
  td: 'border: 1px solid #e5e5e5; padding: 8px 12px; text-align: left;',
  img: 'max-width: 100%; height: auto; display: block; margin: 20px auto; border-radius: 6px; box-shadow: 0 2px 8px rgba(0,0,0,0.06);',
  hr: 'border: none; border-top: 1px dashed #d1d5db; margin: 24px 0;',
  ul: 'margin: 12px 0; padding-left: 20px; color: #3f3f3f;',
  ol: 'margin: 12px 0; padding-left: 20px; color: #3f3f3f;',
  li: 'margin: 6px 0; line-height: 1.7;',
  strong: 'font-weight: 700; color: #1a1a1a;',
  a: 'color: #07c160; text-decoration: underline;',
};

// 2. Tech Theme (极简科技风，深蓝/冷灰/等宽代码)
const TECH_STYLES: WechatBlockStyles = {
  h1: 'font-size: 23px; font-weight: 700; line-height: 1.35; margin: 28px 0 16px; color: #0f172a; border-bottom: 2px solid #2563eb; padding-bottom: 8px;',
  h2: 'font-size: 19px; font-weight: 700; line-height: 1.4; margin: 24px 0 12px; color: #1e3a8a; border-left: 4px solid #2563eb; padding-left: 10px;',
  h3: 'font-size: 16px; font-weight: 600; line-height: 1.4; margin: 18px 0 8px; color: #334155;',
  p: 'margin: 14px 0; text-align: justify; line-height: 1.8; color: #334155; font-size: 15px;',
  blockquote: 'margin: 16px 0; padding: 12px 16px; background: #eff6ff; border-left: 4px solid #3b82f6; color: #1e40af; border-radius: 4px; font-size: 14px;',
  pre: 'background: #0f172a; color: #e2e8f0; padding: 14px; border-radius: 6px; overflow-x: auto; margin: 16px 0; line-height: 1.5; font-size: 13px;',
  code: 'font-family: ui-monospace, SFMono-Regular, monospace; background: #f1f5f9; padding: 2px 6px; border-radius: 4px; font-size: 13px; color: #2563eb;',
  table: 'width: 100%; border-collapse: collapse; margin: 16px 0; font-size: 13px;',
  th: 'border: 1px solid #cbd5e1; padding: 8px 12px; text-align: left; background: #f8fafc; font-weight: 600; color: #0f172a;',
  td: 'border: 1px solid #cbd5e1; padding: 8px 12px; text-align: left;',
  img: 'max-width: 100%; height: auto; display: block; margin: 20px auto; border-radius: 8px; border: 1px solid #e2e8f0;',
  hr: 'border: none; border-top: 1px solid #94a3b8; margin: 24px 0;',
  ul: 'margin: 12px 0; padding-left: 20px; color: #334155;',
  ol: 'margin: 12px 0; padding-left: 20px; color: #334155;',
  li: 'margin: 6px 0; line-height: 1.7;',
  strong: 'font-weight: 700; color: #0f172a;',
  a: 'color: #2563eb; text-decoration: none; border-bottom: 1px solid #2563eb;',
};

// 3. Enterprise Theme (大厂严谨风，深邃藏青/精致表格)
const ENTERPRISE_STYLES: WechatBlockStyles = {
  h1: 'font-size: 22px; font-weight: 700; line-height: 1.4; margin: 28px 0 16px; color: #111827; text-align: center; letter-spacing: 0.5px;',
  h2: 'font-size: 18px; font-weight: 700; line-height: 1.4; margin: 24px 0 12px; color: #111827; border-left: 4px solid #475569; padding-left: 10px;',
  h3: 'font-size: 15px; font-weight: 600; line-height: 1.4; margin: 18px 0 8px; color: #1f2937;',
  p: 'margin: 13px 0; text-align: justify; line-height: 1.75; color: #374151; font-size: 15px;',
  blockquote: 'margin: 16px 0; padding: 12px 14px; background: #f3f4f6; border-left: 4px solid #6b7280; color: #4b5563; font-size: 14px;',
  pre: 'background: #1f2937; color: #f9fafb; padding: 14px; border-radius: 6px; overflow-x: auto; margin: 16px 0; line-height: 1.5; font-size: 13px;',
  code: 'font-family: ui-monospace, SFMono-Regular, monospace; background: #e5e7eb; padding: 2px 6px; border-radius: 4px; font-size: 13px; color: #1f2937;',
  table: 'width: 100%; border-collapse: collapse; margin: 16px 0; font-size: 13px;',
  th: 'border: 1px solid #d1d5db; padding: 8px 12px; text-align: left; background: #f3f4f6; font-weight: 600; color: #111827;',
  td: 'border: 1px solid #d1d5db; padding: 8px 12px; text-align: left;',
  img: 'max-width: 100%; height: auto; display: block; margin: 18px auto; border-radius: 4px;',
  hr: 'border: none; border-top: 1px solid #e5e7eb; margin: 24px 0;',
  ul: 'margin: 12px 0; padding-left: 20px; color: #374151;',
  ol: 'margin: 12px 0; padding-left: 20px; color: #374151;',
  li: 'margin: 5px 0; line-height: 1.65;',
  strong: 'font-weight: 700; color: #111827;',
  a: 'color: #3b82f6; text-decoration: underline;',
};

// 4. Humanist Theme (人文艺术风，暖色调/舒缓行距)
const HUMANIST_STYLES: WechatBlockStyles = {
  h1: 'font-size: 22px; font-weight: 600; line-height: 1.5; margin: 30px 0 16px; color: #78350f; text-align: center; letter-spacing: 1px;',
  h2: 'font-size: 18px; font-weight: 600; line-height: 1.45; margin: 24px 0 12px; color: #92400e; border-left: 3px solid #d97706; padding-left: 12px;',
  h3: 'font-size: 16px; font-weight: 500; line-height: 1.45; margin: 18px 0 8px; color: #b45309;',
  p: 'margin: 16px 0; text-align: justify; line-height: 1.9; color: #451a03; font-size: 15px;',
  blockquote: 'margin: 18px 0; padding: 14px 18px; background: #fef3c7; border-left: 3px solid #f59e0b; color: #78350f; font-size: 14px; font-style: italic;',
  pre: 'background: #292524; color: #e7e5e4; padding: 14px; border-radius: 6px; overflow-x: auto; margin: 16px 0; line-height: 1.5; font-size: 13px;',
  code: 'font-family: ui-monospace, SFMono-Regular, monospace; background: #fef3c7; padding: 2px 6px; border-radius: 4px; font-size: 13px; color: #b45309;',
  table: 'width: 100%; border-collapse: collapse; margin: 16px 0; font-size: 13px;',
  th: 'border: 1px solid #fde68a; padding: 8px 12px; text-align: left; background: #fef3c7; font-weight: 600; color: #78350f;',
  td: 'border: 1px solid #fde68a; padding: 8px 12px; text-align: left;',
  img: 'max-width: 100%; height: auto; display: block; margin: 20px auto; border-radius: 8px; box-shadow: 0 4px 12px rgba(180, 83, 9, 0.08);',
  hr: 'border: none; border-top: 1px solid #fcd34d; margin: 28px 0;',
  ul: 'margin: 12px 0; padding-left: 20px; color: #451a03;',
  ol: 'margin: 12px 0; padding-left: 20px; color: #451a03;',
  li: 'margin: 6px 0; line-height: 1.8;',
  strong: 'font-weight: 600; color: #78350f;',
  a: 'color: #b45309; text-decoration: underline;',
};

export const WECHAT_THEMES: Record<WechatThemeId, WechatThemeConfig> = {
  classic: {
    id: 'classic',
    name: '经典绿标 (Classic)',
    primaryColor: '#07c160',
    accentColor: '#f6f6f6',
    fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", sans-serif',
    styles: CLASSIC_STYLES,
  },
  tech: {
    id: 'tech',
    name: '极简科技 (Tech)',
    primaryColor: '#2563eb',
    accentColor: '#eff6ff',
    fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
    styles: TECH_STYLES,
  },
  enterprise: {
    id: 'enterprise',
    name: '大厂严谨 (Enterprise)',
    primaryColor: '#1e293b',
    accentColor: '#f3f4f6',
    fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
    styles: ENTERPRISE_STYLES,
  },
  humanist: {
    id: 'humanist',
    name: '人文艺术 (Humanist)',
    primaryColor: '#d97706',
    accentColor: '#fef3c7',
    fontFamily: 'Georgia, Cambria, "Songti SC", "SimSun", serif',
    styles: HUMANIST_STYLES,
  },
};

export function getWechatTheme(themeId: WechatThemeId): WechatThemeConfig {
  return WECHAT_THEMES[themeId] ?? WECHAT_THEMES.classic;
}

/**
 * Inlines WeChat Official Account styles directly onto HTML tags.
 */
export function compileWechatInlineHtml(
  rawContent: string,
  themeId: WechatThemeId = 'classic',
  scale: FontSizeScale = 'normal'
): string {
  if (!rawContent || !rawContent.trim()) {
    return '<section><p style="color:#94a3b8;">(暂无排版内容)</p></section>';
  }

  const theme = getWechatTheme(themeId);
  const scaleMultiplier = FONT_SCALES[scale];

  // Convert basic Markdown to semantic HTML if not already HTML
  let workingHtml = rawContent;
  const isHtml = /<[a-z][\s\S]*>/i.test(rawContent);

  if (!isHtml) {
    // Simple robust markdown-to-html conversion
    workingHtml = rawContent
      .replace(/^### (.*$)/gim, '<h3>$1</h3>')
      .replace(/^## (.*$)/gim, '<h2>$1</h2>')
      .replace(/^# (.*$)/gim, '<h1>$1</h1>')
      .replace(/^> (.*$)/gim, '<blockquote>$1</blockquote>')
      .replace(/\*\*(.*?)\*\*/gim, '<strong>$1</strong>')
      .replace(/\*(.*?)\*/gim, '<em>$1</em>')
      .replace(/!\[(.*?)\]\((.*?)\)/gim, '<img alt="$1" src="$2" />')
      .replace(/\[(.*?)\]\((.*?)\)/gim, '<a href="$2">$1</a>')
      .replace(/\n\n+/g, '</p><p>')
      .replace(/^([^<].*)/gim, '<p>$1</p>');
  }

  // Tag list for inline injection
  const tags: (keyof WechatBlockStyles)[] = [
    'h1',
    'h2',
    'h3',
    'p',
    'blockquote',
    'pre',
    'code',
    'table',
    'th',
    'td',
    'img',
    'hr',
    'ul',
    'ol',
    'li',
    'strong',
    'a',
  ];

  for (const tag of tags) {
    let blockStyle = theme.styles[tag];
    if (scaleMultiplier !== 1.0) {
      blockStyle = blockStyle.replace(/font-size:\s*(\d+)px/g, (_, px) => {
        const adjusted = Math.round(Number(px) * scaleMultiplier);
        return `font-size: ${adjusted}px`;
      });
    }

    const regex = new RegExp(`<${tag}(\\b[^>]*)>`, 'gi');
    workingHtml = workingHtml.replace(regex, (match, attrs) => {
      if (/style=["']/i.test(attrs)) {
        return `<${tag}${attrs.replace(/style=["']([^"']*)["']/i, (_m: string, s: string) => `style="${s.trim().replace(/;?$/, ';')} ${blockStyle}"`)}>`;
      }
      return `<${tag}${attrs} style="${blockStyle}">`;
    });
  }

  return `<section style="font-family: ${theme.fontFamily}; max-width: 100%; box-sizing: border-box; word-break: break-word;">${workingHtml}</section>`;
}
