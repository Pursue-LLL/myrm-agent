export type { ThemeProfileIndexEntry, ThemeProfileRecipe, ThemeLayoutId, CompiledTheme } from './schema';
export { compileThemeProfile, applyCompiledTheme, applyThemeFont, clearThemeRuntime } from './compiler';
export { resolveLayoutFromPathname } from './route-layout';
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
export { THEME_PREINIT_STORAGE_KEY, writeThemePreinitSnapshot } from './preinit';
export type { ThemePreinitSnapshot } from './preinit';
export { meetsContrast, contrastRatio, derivePalette } from './oklch';
export { THEME_LAYOUT_CATALOG, getLayoutCatalogItem } from './layout-catalog';
export type { ThemeLayoutCatalogItem } from './layout-catalog';
export { parseThemeRecipeJson, ThemeRecipeParseError } from './parse-recipe';
export type { ThemeRecipeParseErrorCode } from './parse-recipe';
export {
  STUDIO_PREVIEW_PROFILE_ID,
  stripStudioPreviewProfiles,
  sanitizeActiveThemeProfileId,
} from './studio-constants';
