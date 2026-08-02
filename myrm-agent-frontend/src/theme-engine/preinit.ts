import type { CompiledTheme, ThemeLayoutId, ThemeReadabilityScene } from './schema';

export const THEME_PREINIT_STORAGE_KEY = 'myrm-theme-preinit';

export interface ThemePreinitSnapshot {
  profileId: string;
  layoutId: ThemeLayoutId;
  sceneId: ThemeReadabilityScene;
  artOn: boolean;
  dualAccent: boolean;
  isDark: boolean;
  primary: string;
  primaryForeground: string;
  primaryHover: string;
  accentWarm?: string;
  artPosterUrl?: string;
  artWash?: number;
}

export interface ThemePreinitWriteOptions {
  artPosterUrl?: string | null;
  artWash?: number;
}

export function writeThemePreinitSnapshot(
  compiled: CompiledTheme,
  colorScheme: 'light' | 'dark',
  layoutId: ThemeLayoutId,
  sceneId: ThemeReadabilityScene,
  options: ThemePreinitWriteOptions = {},
): void {
  if (typeof window === 'undefined') {
    return;
  }
  const snapshot: ThemePreinitSnapshot = {
    profileId: compiled.dataAttributes['data-myrm-theme-profile'] ?? 'official-default',
    layoutId,
    sceneId,
    artOn: compiled.dataAttributes['data-myrm-theme-art'] === 'on',
    dualAccent: compiled.dataAttributes['data-myrm-theme-dual-accent'] === 'true',
    isDark: colorScheme === 'dark',
    primary: compiled.cssVariables['--primary'] ?? '',
    primaryForeground: compiled.cssVariables['--primary-foreground'] ?? '',
    primaryHover: compiled.cssVariables['--primary-hover'] ?? '',
    accentWarm: compiled.cssVariables['--accent-warm'],
  };
  if (options.artPosterUrl) {
    snapshot.artPosterUrl = options.artPosterUrl;
  }
  if (typeof options.artWash === 'number') {
    snapshot.artWash = options.artWash;
  }
  try {
    localStorage.setItem(THEME_PREINIT_STORAGE_KEY, JSON.stringify(snapshot));
  } catch {
    /* storage quota — pre-init falls back to official default */
  }
}
