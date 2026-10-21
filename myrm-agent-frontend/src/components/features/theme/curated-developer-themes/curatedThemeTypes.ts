/**
 * [INPUT]
 * - None (纯类型与契约定义)
 *
 * [OUTPUT]
 * - CuratedThemeId: 精选极客主题唯一标识枚举
 * - CuratedThemePreset: 主题调色盘与语义化 Token 契约
 * - CuratedThemeState: 主题管理器状态机
 *
 * [POS]
 * 精选工程师高对比度终端/界面暗色主题矩阵的核心数据结构与类型定义。
 */

export type CuratedThemeId =
  | 'default-dark'
  | 'tokyo-night'
  | 'catppuccin-mocha'
  | 'gruvbox-dark'
  | 'nord'
  | 'dracula-pro'
  | 'cyberpunk-neon';

export interface SemanticThemeTokens {
  background: string;
  foreground: string;
  card: string;
  cardForeground: string;
  border: string;
  primary: string;
  primaryForeground: string;
  accent: string;
  accentForeground: string;
  muted: string;
  mutedForeground: string;
}

export interface TerminalAnsiPalette {
  black: string;
  red: string;
  green: string;
  yellow: string;
  blue: string;
  magenta: string;
  cyan: string;
  white: string;
}

export interface CuratedThemePreset {
  id: CuratedThemeId;
  name: string;
  tagline: string;
  contrastRatio: string;
  accentColor: string;
  surfaceColor: string;
  previewPalette: readonly string[];
  tokens: SemanticThemeTokens;
  ansi: TerminalAnsiPalette;
}

export interface CuratedThemeState {
  activeThemeId: CuratedThemeId;
  customThemes: CuratedThemePreset[];
  syncWithSystemDark: boolean;
  setTheme: (id: CuratedThemeId) => void;
  setSyncWithSystemDark: (sync: boolean) => void;
  resetToDefault: () => void;
}
