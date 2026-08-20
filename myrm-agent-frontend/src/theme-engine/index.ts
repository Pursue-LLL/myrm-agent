export type {
  ThemeProfileIndexEntry,
  ThemeProfileRecipe,
  ThemeLayoutId,
  ThemeReadabilityScene,
  CompiledTheme,
  ThemeMediaKind,
} from './schema';
export { compileThemeProfile, applyCompiledTheme, applyThemeFont, clearThemeRuntime } from './compiler';
export { resolveReadabilityScene, FUNCTIONAL_ROUTE_PREFIXES, STATIC_APP_SEGMENTS } from './readability-scene';
export {
  effectiveArtWash,
  mergeSceneSurfaces,
  FUNCTIONAL_ART_WASH_FLOOR,
  FUNCTIONAL_SURFACE_FLOORS,
} from './scene-surfaces';
export {
  BUILTIN_THEME_PROFILES,
  OFFICIAL_DEFAULT_PROFILE_ID,
  getBuiltinProfile,
  getDefaultThemeProfile,
} from './presets';
export {
  USER_ART_OVERLAY_ID,
  ART_WASH_MIN,
  ART_WASH_MAX,
  EMPTY_THEME_PROFILES,
  mergeArtOverlay,
  buildArtOverlayProfile,
  upsertArtOverlayProfile,
  stripArtOverlay,
  hasArtOverlay,
  getArtOverlayProfile,
  updateArtOverlayWash,
  mediaKindFromMime,
  mediaKindFromFile,
  validateThemeBackgroundFile,
} from './overlay';
export type { ThemeBackgroundValidationError } from './overlay';
export { THEME_PREINIT_STORAGE_KEY, applyThemePreinitFromLocalStorage, writeThemePreinitSnapshot } from './preinit';
export type { ThemePreinitSnapshot } from './preinit';
export { meetsContrast, contrastRatio, derivePalette, resolveContrastSafeForeground } from './oklch';
export { recommendLayoutFromAspect } from './recommend-layout-from-aspect';
export { sampleHeroImageBlob, sampleHeroImageData, type HeroImageSample } from './sample-hero-image';
export { THEME_LAYOUT_CATALOG, getLayoutCatalogItem } from './layout-catalog';
export type { ThemeLayoutCatalogItem } from './layout-catalog';
export { parseThemeRecipeJson, ThemeRecipeParseError } from './parse-recipe';
export type { ThemeRecipeParseErrorCode } from './parse-recipe';
export {
  STUDIO_PREVIEW_PROFILE_ID,
  stripStudioPreviewProfiles,
  sanitizeActiveThemeProfileId,
} from './studio-constants';
export {
  buildOfficialThemeRestorePatch,
  isThemeDeviatedFromOfficial,
  needsRestoreConfirm,
  type ThemeRestoreState,
  type OfficialThemeRestorePatch,
} from './official-restore';
