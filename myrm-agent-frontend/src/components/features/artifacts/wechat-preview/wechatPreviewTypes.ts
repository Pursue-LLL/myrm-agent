/**
 * [INPUT]
 * - None (pure TypeScript type definitions)
 *
 * [OUTPUT]
 * - DeviceViewportMode, WechatThemeId, WechatThemeConfig, FontSizeScale, MultiDeviceArticlePreviewerProps
 *
 * [POS]
 * Type definitions for WeChat Social Article Formatter & Multi-Device Previewer (Item 45 P0).
 * Strictly under 80 lines. Zero `any`.
 */

export type DeviceViewportMode = 'mobile' | 'tablet' | 'desktop';

export type WechatThemeId = 'classic' | 'tech' | 'enterprise' | 'humanist';

export type FontSizeScale = 'compact' | 'normal' | 'spacious';

export interface WechatBlockStyles {
  h1: string;
  h2: string;
  h3: string;
  p: string;
  blockquote: string;
  pre: string;
  code: string;
  table: string;
  th: string;
  td: string;
  img: string;
  hr: string;
  ul: string;
  ol: string;
  li: string;
  strong: string;
  a: string;
}

export interface WechatThemeConfig {
  id: WechatThemeId;
  name: string;
  primaryColor: string;
  accentColor: string;
  fontFamily: string;
  styles: WechatBlockStyles;
}

export interface MultiDeviceArticlePreviewerProps {
  content: string; // Markdown or HTML source
  title?: string;
  filename?: string;
  className?: string;
  onCopySuccess?: () => void;
}
