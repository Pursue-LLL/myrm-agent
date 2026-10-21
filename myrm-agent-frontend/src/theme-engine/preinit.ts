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

function readThemePreinitSnapshot(): ThemePreinitSnapshot | null {
  if (typeof window === 'undefined') {
    return null;
  }
  try {
    const raw = localStorage.getItem(THEME_PREINIT_STORAGE_KEY);
    if (!raw) {
      return null;
    }
    const parsed: unknown = JSON.parse(raw);
    if (!parsed || typeof parsed !== 'object') {
      return null;
    }
    return parsed as ThemePreinitSnapshot;
  } catch {
    return null;
  }
}

/** Apply persisted workspace theme tokens (e.g. popped-out pet overlay on storage sync). */
export function applyThemePreinitFromLocalStorage(root: HTMLElement = document.documentElement): boolean {
  const snapshot = readThemePreinitSnapshot();
  if (!snapshot) {
    return false;
  }

  root.classList.toggle('dark', snapshot.isDark);
  root.classList.toggle('light', !snapshot.isDark);

  root.setAttribute('data-myrm-theme-profile', snapshot.profileId);
  root.setAttribute('data-myrm-theme-layout', snapshot.layoutId);
  root.setAttribute('data-myrm-theme-scene', snapshot.sceneId);
  root.setAttribute('data-myrm-theme-art', snapshot.artOn ? 'on' : 'off');
  root.setAttribute('data-myrm-theme-dual-accent', snapshot.dualAccent ? 'true' : 'false');

  if (snapshot.primary) {
    root.style.setProperty('--primary', snapshot.primary);
    root.style.setProperty('--primary-foreground', snapshot.primaryForeground);
    root.style.setProperty('--primary-hover', snapshot.primaryHover);
  }
  if (snapshot.accentWarm) {
    root.style.setProperty('--accent-warm', snapshot.accentWarm);
  }

  return true;
}
