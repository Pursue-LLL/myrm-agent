import type { ThemeLayoutId } from './schema';

export interface LayoutSurfaceTokens {
  navOpacity: number;
  sidebarOpacity: number;
  mainOpacity: number;
  surfaceOpacity: number;
  wash: number;
}

const LAYOUT_SURFACES: Record<ThemeLayoutId, LayoutSurfaceTokens> = {
  'full-bleed': {
    navOpacity: 0.62,
    sidebarOpacity: 0.58,
    mainOpacity: 0.72,
    surfaceOpacity: 0.78,
    wash: 0.42,
  },
  'nav-rail-focus': {
    navOpacity: 0.82,
    sidebarOpacity: 0.74,
    mainOpacity: 0.68,
    surfaceOpacity: 0.84,
    wash: 0.48,
  },
  'chat-hero': {
    navOpacity: 0.66,
    sidebarOpacity: 0.6,
    mainOpacity: 0.64,
    surfaceOpacity: 0.76,
    wash: 0.38,
  },
  'work-dense': {
    navOpacity: 0.92,
    sidebarOpacity: 0.9,
    mainOpacity: 0.94,
    surfaceOpacity: 0.96,
    wash: 0.62,
  },
};

export function getLayoutSurfaces(layoutId: ThemeLayoutId): LayoutSurfaceTokens {
  return LAYOUT_SURFACES[layoutId];
}
