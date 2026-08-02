import { getLayoutSurfaces, type LayoutSurfaceTokens } from './layouts';
import type { ThemeLayoutId, ThemeReadabilityScene } from './schema';

/** Minimum art wash overlay on functional pages (MP4/image readability). */
export const FUNCTIONAL_ART_WASH_FLOOR = 0.55;

const FUNCTIONAL_SURFACE_FLOORS: LayoutSurfaceTokens = {
  navOpacity: 0.92,
  sidebarOpacity: 0.9,
  mainOpacity: 0.94,
  surfaceOpacity: 0.96,
  wash: FUNCTIONAL_ART_WASH_FLOOR,
};

function clampOpacity(value: number): number {
  return Math.min(1, Math.max(0, value));
}

export function mergeSceneSurfaces(
  layoutId: ThemeLayoutId,
  sceneId: ThemeReadabilityScene,
): LayoutSurfaceTokens {
  const layout = getLayoutSurfaces(layoutId);
  if (sceneId === 'immersive') {
    return layout;
  }
  return {
    navOpacity: clampOpacity(Math.max(layout.navOpacity, FUNCTIONAL_SURFACE_FLOORS.navOpacity)),
    sidebarOpacity: clampOpacity(
      Math.max(layout.sidebarOpacity, FUNCTIONAL_SURFACE_FLOORS.sidebarOpacity),
    ),
    mainOpacity: clampOpacity(Math.max(layout.mainOpacity, FUNCTIONAL_SURFACE_FLOORS.mainOpacity)),
    surfaceOpacity: clampOpacity(
      Math.max(layout.surfaceOpacity, FUNCTIONAL_SURFACE_FLOORS.surfaceOpacity),
    ),
    wash: layout.wash,
  };
}

export function effectiveArtWash(recipeWash: number, sceneId: ThemeReadabilityScene): number {
  if (sceneId === 'immersive') {
    return recipeWash;
  }
  return Math.max(recipeWash, FUNCTIONAL_ART_WASH_FLOOR);
}
