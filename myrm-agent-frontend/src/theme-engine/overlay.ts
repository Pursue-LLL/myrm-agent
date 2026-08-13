import type { ThemeMediaKind, ThemeProfileRecipe } from './schema';

export const USER_ART_OVERLAY_ID = 'user-art-overlay';
export const ART_WASH_MIN = 0.2;
export const ART_WASH_MAX = 0.8;

/** Stable fallback — never inline `?? []` in zustand selectors (new ref every render → ThemeProfileProvider loop). */
export const EMPTY_THEME_PROFILES: ThemeProfileRecipe[] = [];

const MAX_THEME_ASSET_BYTES = 80 * 1024 * 1024;
const ALLOWED_THEME_MIMES = new Set(['image/png', 'image/jpeg', 'image/webp', 'video/mp4']);

export type ThemeBackgroundValidationError = 'invalidType' | 'tooLarge' | 'empty';

export function validateThemeBackgroundFile(file: File): ThemeBackgroundValidationError | null {
  if (file.size === 0) {return 'empty';}
  const ext = file.name.split('.').pop()?.toLowerCase() ?? '';
  const allowedExt = ext === 'jpg' || ext === 'jpeg' || ext === 'png' || ext === 'webp' || ext === 'mp4';
  if (!ALLOWED_THEME_MIMES.has(file.type) && !allowedExt) {
    return 'invalidType';
  }
  if (file.size > MAX_THEME_ASSET_BYTES) {
    return 'tooLarge';
  }
  return null;
}

export function mergeArtOverlay(
  base: ThemeProfileRecipe,
  customProfiles: ThemeProfileRecipe[],
): ThemeProfileRecipe {
  const overlay = customProfiles.find((profile) => profile.id === USER_ART_OVERLAY_ID);
  if (!overlay?.art || overlay.art.mediaKind === 'none' || !overlay.art.assetRef) {
    return base;
  }
  return {
    ...base,
    art: {
      ...base.art,
      mediaKind: overlay.art.mediaKind,
      assetRef: overlay.art.assetRef,
      posterAssetRef: overlay.art.posterAssetRef ?? overlay.art.assetRef,
      focusX: overlay.art.focusX,
      focusY: overlay.art.focusY,
      wash: overlay.art.wash,
    },
  };
}

export function buildArtOverlayProfile(
  base: ThemeProfileRecipe,
  assetRef: string,
  mediaKind: Exclude<ThemeMediaKind, 'none'>,
  posterAssetRef?: string | null,
): ThemeProfileRecipe {
  const resolvedPoster =
    mediaKind === 'image' ? assetRef : (posterAssetRef ?? null);
  return {
    id: USER_ART_OVERLAY_ID,
    name: 'Workspace background',
    layoutId: base.layoutId,
    fontId: base.fontId,
    builtin: false,
    palette: base.palette,
    art: {
      focusX: base.art.focusX,
      focusY: base.art.focusY,
      wash: base.art.wash,
      mediaKind,
      assetRef,
      posterAssetRef: resolvedPoster,
    },
  };
}

export function upsertArtOverlayProfile(
  profiles: ThemeProfileRecipe[],
  overlay: ThemeProfileRecipe,
): ThemeProfileRecipe[] {
  const withoutOverlay = stripArtOverlay(profiles);
  return [...withoutOverlay, overlay];
}

export function stripArtOverlay(profiles: ThemeProfileRecipe[]): ThemeProfileRecipe[] {
  return profiles.filter((profile) => profile.id !== USER_ART_OVERLAY_ID);
}

export function hasArtOverlay(profiles: ThemeProfileRecipe[]): boolean {
  return getArtOverlayProfile(profiles) !== null;
}

export function getArtOverlayProfile(profiles: ThemeProfileRecipe[]): ThemeProfileRecipe | null {
  const overlay = profiles.find((profile) => profile.id === USER_ART_OVERLAY_ID);
  if (!overlay?.art.assetRef || overlay.art.mediaKind === 'none') {
    return null;
  }
  return overlay;
}

export function updateArtOverlayWash(profiles: ThemeProfileRecipe[], wash: number): ThemeProfileRecipe[] {
  const overlay = getArtOverlayProfile(profiles);
  if (!overlay) {
    return profiles;
  }
  const clamped = Math.min(ART_WASH_MAX, Math.max(ART_WASH_MIN, wash));
  return upsertArtOverlayProfile(profiles, {
    ...overlay,
    art: {
      ...overlay.art,
      wash: clamped,
    },
  });
}

export function mediaKindFromMime(mimeType: string): Exclude<ThemeMediaKind, 'none'> {
  return mimeType.startsWith('video/') ? 'video' : 'image';
}

export function mediaKindFromFile(file: File): Exclude<ThemeMediaKind, 'none'> {
  if (file.type.startsWith('video/')) {
    return 'video';
  }
  const ext = file.name.split('.').pop()?.toLowerCase() ?? '';
  if (ext === 'mp4') {
    return 'video';
  }
  return mediaKindFromMime(file.type);
}
