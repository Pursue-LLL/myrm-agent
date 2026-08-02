import type { ThemeProfileRecipe } from './schema';

const BASE_ART = {
  focusX: 0.5,
  focusY: 0.42,
  wash: 0.46,
  mediaKind: 'none' as const,
  assetRef: null,
  posterAssetRef: null,
};

export const OFFICIAL_DEFAULT_PROFILE_ID = 'official-default';

export const BUILTIN_THEME_PROFILES: ThemeProfileRecipe[] = [
  {
    id: OFFICIAL_DEFAULT_PROFILE_ID,
    name: 'Official Default',
    layoutId: 'full-bleed',
    fontId: 'inter',
    builtin: true,
    palette: {
      primaryLight: '#588e95',
      primaryDark: '#6ba3aa',
      primaryHoverLight: '#4a7d84',
      primaryHoverDark: '#7eb5bc',
      primaryDarkLight: '#10505a',
      primaryDarkDark: '#588e95',
      accentWarmLight: '#e07830',
      accentWarmDark: '#f5b868',
      dualAccent: true,
    },
    art: { ...BASE_ART },
  },
  {
    id: 'preset-teal',
    name: 'Teal',
    layoutId: 'nav-rail-focus',
    fontId: 'inter',
    builtin: true,
    palette: {
      primaryLight: '#588e95',
      primaryDark: '#6ba3aa',
      primaryHoverLight: '#4a7d84',
      primaryHoverDark: '#7eb5bc',
      primaryDarkLight: '#10505a',
      primaryDarkDark: '#588e95',
      dualAccent: false,
    },
    art: { ...BASE_ART },
  },
  {
    id: 'preset-rose',
    name: 'Rose',
    layoutId: 'chat-hero',
    fontId: 'inter',
    builtin: true,
    palette: {
      primaryLight: '#c4567a',
      primaryDark: '#f472b6',
      primaryHoverLight: '#a8425f',
      primaryHoverDark: '#ec4899',
      primaryDarkLight: '#8c3050',
      primaryDarkDark: '#db2777',
      dualAccent: false,
    },
    art: { ...BASE_ART },
  },
  {
    id: 'preset-amber',
    name: 'Amber',
    layoutId: 'full-bleed',
    fontId: 'inter',
    builtin: true,
    palette: {
      primaryLight: '#b4762c',
      primaryDark: '#fbbf24',
      primaryHoverLight: '#996320',
      primaryHoverDark: '#f59e0b',
      primaryDarkLight: '#7d5018',
      primaryDarkDark: '#d97706',
      dualAccent: false,
    },
    art: { ...BASE_ART },
  },
  {
    id: 'preset-violet',
    name: 'Violet',
    layoutId: 'nav-rail-focus',
    fontId: 'inter',
    builtin: true,
    palette: {
      primaryLight: '#7c4dba',
      primaryDark: '#a78bfa',
      primaryHoverLight: '#6b3fa4',
      primaryHoverDark: '#8b5cf6',
      primaryDarkLight: '#5a338e',
      primaryDarkDark: '#7c3aed',
      dualAccent: false,
    },
    art: { ...BASE_ART },
  },
  {
    id: 'preset-ocean',
    name: 'Ocean',
    layoutId: 'chat-hero',
    fontId: 'inter',
    builtin: true,
    palette: {
      primaryLight: '#2563eb',
      primaryDark: '#60a5fa',
      primaryHoverLight: '#1d4ed8',
      primaryHoverDark: '#3b82f6',
      primaryDarkLight: '#1e40af',
      primaryDarkDark: '#2563eb',
      dualAccent: false,
    },
    art: { ...BASE_ART },
  },
  {
    id: 'preset-atkinson-calm',
    name: 'Calm Readable',
    layoutId: 'work-dense',
    fontId: 'atkinson',
    builtin: true,
    palette: {
      primaryLight: '#4a7d84',
      primaryDark: '#6ba3aa',
      primaryHoverLight: '#3d6b72',
      primaryHoverDark: '#7eb5bc',
      primaryDarkLight: '#2f555b',
      primaryDarkDark: '#588e95',
      dualAccent: false,
    },
    art: { ...BASE_ART, wash: 0.58 },
  },
];

export function getBuiltinProfile(id: string): ThemeProfileRecipe | undefined {
  return BUILTIN_THEME_PROFILES.find((profile) => profile.id === id);
}

export function getDefaultThemeProfile(): ThemeProfileRecipe {
  return BUILTIN_THEME_PROFILES[0];
}
