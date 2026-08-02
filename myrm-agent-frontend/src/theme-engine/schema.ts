import type { FontId } from '@/lib/fonts';

export type ThemeLayoutId = 'full-bleed' | 'nav-rail-focus' | 'chat-hero' | 'work-dense';

export type ThemeReadabilityScene = 'immersive' | 'functional';

export type ThemeMediaKind = 'none' | 'image' | 'video';

export interface ThemePaletteTokens {
  primaryLight: string;
  primaryDark: string;
  primaryHoverLight: string;
  primaryHoverDark: string;
  primaryDarkLight: string;
  primaryDarkDark: string;
  accentWarmLight?: string;
  accentWarmDark?: string;
  dualAccent: boolean;
}

export interface ThemeArtConfig {
  focusX: number;
  focusY: number;
  wash: number;
  mediaKind: ThemeMediaKind;
  assetRef?: string | null;
  posterAssetRef?: string | null;
}

export interface ThemeProfileRecipe {
  id: string;
  name: string;
  layoutId: ThemeLayoutId;
  fontId: FontId;
  palette: ThemePaletteTokens;
  art: ThemeArtConfig;
  builtin: boolean;
  packageDescription?: string | null;
  packageTagline?: string | null;
  packageAuthor?: string | null;
  packagePreviewAssetRef?: string | null;
}

export interface ThemeCompileContext {
  colorScheme: 'light' | 'dark';
  layoutId: ThemeLayoutId;
  sceneId: ThemeReadabilityScene;
  prefersReducedMotion: boolean;
  isMobile: boolean;
}

export interface CompiledThemeArtLayer {
  enabled: boolean;
  mediaKind: ThemeMediaKind;
  mediaUrl: string | null;
  posterUrl: string | null;
  focusX: number;
  focusY: number;
  wash: number;
  surfaceOpacity: number;
  navOpacity: number;
  sidebarOpacity: number;
  mainOpacity: number;
}

export interface CompiledTheme {
  cssVariables: Record<string, string>;
  dataAttributes: Record<string, string>;
  artLayer: CompiledThemeArtLayer;
  fontId: FontId;
}

export interface ThemeProfileIndexEntry {
  id: string;
  name: string;
  layoutId: ThemeLayoutId;
  fontId: FontId;
  palette: ThemePaletteTokens;
  art: ThemeArtConfig;
  builtin: boolean;
}
