/**
 * [INPUT]
 * - ./curatedThemeTypes::CuratedThemeId, CuratedThemePreset, CuratedThemeState
 * - ./curatedThemePresets::CURATED_DEVELOPER_THEMES, getCuratedThemeById
 * - zustand::create
 *
 * [OUTPUT]
 * - useCuratedThemeStore: 极客主题状态机与 CSS 变量原生映射管理器
 * - applyCuratedThemeVariables: DOM CSS 变量注入函数
 *
 * [POS]
 * 精选工程师高对比度终端/界面暗色主题矩阵的持久化存储与零运行时开销 DOM 变量注入层。
 */

import { create } from 'zustand';
import type { CuratedThemeId, CuratedThemePreset, CuratedThemeState } from './curatedThemeTypes';
import { getCuratedThemeById } from './curatedThemePresets';

const STORAGE_KEY = 'myrm_curated_developer_theme';
const SYNC_STORAGE_KEY = 'myrm_curated_theme_sync_system';

export function applyCuratedThemeVariables(theme: CuratedThemePreset | null): void {
  if (typeof document === 'undefined') {
    return;
  }
  const root = document.documentElement;

  if (!theme || theme.id === 'default-dark') {
    root.removeAttribute('data-curated-theme');
    const varNames = [
      '--curated-bg',
      '--curated-fg',
      '--curated-card',
      '--curated-card-fg',
      '--curated-border',
      '--curated-primary',
      '--curated-primary-fg',
      '--curated-accent',
      '--curated-accent-fg',
      '--curated-muted',
      '--curated-muted-fg',
      '--curated-ansi-black',
      '--curated-ansi-red',
      '--curated-ansi-green',
      '--curated-ansi-yellow',
      '--curated-ansi-blue',
      '--curated-ansi-magenta',
      '--curated-ansi-cyan',
      '--curated-ansi-white',
    ];
    for (const v of varNames) {
      root.style.removeProperty(v);
    }
    return;
  }

  root.setAttribute('data-curated-theme', theme.id);
  const { tokens, ansi } = theme;

  root.style.setProperty('--curated-bg', tokens.background);
  root.style.setProperty('--curated-fg', tokens.foreground);
  root.style.setProperty('--curated-card', tokens.card);
  root.style.setProperty('--curated-card-fg', tokens.cardForeground);
  root.style.setProperty('--curated-border', tokens.border);
  root.style.setProperty('--curated-primary', tokens.primary);
  root.style.setProperty('--curated-primary-fg', tokens.primaryForeground);
  root.style.setProperty('--curated-accent', tokens.accent);
  root.style.setProperty('--curated-accent-fg', tokens.accentForeground);
  root.style.setProperty('--curated-muted', tokens.muted);
  root.style.setProperty('--curated-muted-fg', tokens.mutedForeground);

  root.style.setProperty('--curated-ansi-black', ansi.black);
  root.style.setProperty('--curated-ansi-red', ansi.red);
  root.style.setProperty('--curated-ansi-green', ansi.green);
  root.style.setProperty('--curated-ansi-yellow', ansi.yellow);
  root.style.setProperty('--curated-ansi-blue', ansi.blue);
  root.style.setProperty('--curated-ansi-magenta', ansi.magenta);
  root.style.setProperty('--curated-ansi-cyan', ansi.cyan);
  root.style.setProperty('--curated-ansi-white', ansi.white);
}

function getInitialThemeId(): CuratedThemeId {
  if (typeof window === 'undefined') {
    return 'default-dark';
  }
  try {
    const saved = localStorage.getItem(STORAGE_KEY) as CuratedThemeId | null;
    if (saved && (saved === 'default-dark' || getCuratedThemeById(saved))) {
      return saved;
    }
  } catch {
    // Ignore localStorage access failures
  }
  return 'default-dark';
}

function getInitialSyncPreference(): boolean {
  if (typeof window === 'undefined') {
    return true;
  }
  try {
    const saved = localStorage.getItem(SYNC_STORAGE_KEY);
    return saved !== 'false';
  } catch {
    return true;
  }
}

export const useCuratedThemeStore = create<CuratedThemeState>((set, get) => {
  const initialId = getInitialThemeId();
  if (typeof window !== 'undefined' && initialId !== 'default-dark') {
    const initialTheme = getCuratedThemeById(initialId);
    if (initialTheme) {
      applyCuratedThemeVariables(initialTheme);
    }
  }

  return {
    activeThemeId: initialId,
    customThemes: [],
    syncWithSystemDark: getInitialSyncPreference(),

    setTheme: (id: CuratedThemeId) => {
      set({ activeThemeId: id });
      try {
        localStorage.setItem(STORAGE_KEY, id);
      } catch {
        // Ignore localStorage error
      }
      const targetTheme = id === 'default-dark' ? null : getCuratedThemeById(id) || null;
      applyCuratedThemeVariables(targetTheme);
    },

    setSyncWithSystemDark: (sync: boolean) => {
      set({ syncWithSystemDark: sync });
      try {
        localStorage.setItem(SYNC_STORAGE_KEY, String(sync));
      } catch {
        // Ignore localStorage error
      }
    },

    resetToDefault: () => {
      get().setTheme('default-dark');
    },
  };
});
